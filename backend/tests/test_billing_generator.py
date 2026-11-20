from calendar import monthrange
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from billing.models import Charge, ChargeStatus
from billing.services import (
    generate_charges_for_all_plans,
    generate_missing_charges,
    lock_due_charges,
    refresh_unlocked_charges,
    activate_ended_trials,
)
from core.choices import Currency, PaymentMethod
from plans import services as plan_services
from plans.models import CycleUnit, ExchangeRate, PlanMode, PriceChange, RenewalType, Subscription, SubscriptionStatus


@pytest.fixture
def owner(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        email="bill@example.com", password="pass12345", name="Bill", email_verified=True
    )


def month_before(d: date) -> date:
    y, m = d.year, d.month
    if m == 1:
        last = monthrange(y - 1, 12)[1]
        return date(y - 1, 12, min(d.day, last))
    last = monthrange(y, m - 1)[1]
    return date(y, m - 1, min(d.day, last))


def _plan(owner, **kwargs):
    from catalog.models import Category, ServiceName

    streaming = Category.objects.filter(is_preset=True, name="Streaming").first()
    sn = ServiceName.objects.filter(is_preset=True, category=streaming).first()
    defaults = dict(
        owner=owner,
        service_name=sn,
        category=streaming,
        plan_name="Bill Plan",
        plan_mode=PlanMode.OWNER,
        currency=Currency.BDT,
        cycle_unit=CycleUnit.MONTH,
        cycle_count=1,
        anchor_day=5,
        start_date=date(2026, 1, 5),
        trial_end_date=None,
        renewal_type=RenewalType.AUTO,
        end_date=None,
        status=SubscriptionStatus.ACTIVE,
        recommended_method=PaymentMethod.BKASH,
        billing_from=date(2026, 1, 5),
    )
    defaults.update(kwargs)
    sub = Subscription.objects.create(**defaults)
    PriceChange.objects.create(
        subscription=sub, amount=Decimal("100.00"), currency=sub.currency, effective_from=sub.start_date
    )
    return sub


@pytest.mark.django_db
def test_generate_within_lead_window(owner):
    today = date(2026, 1, 26)
    sub = _plan(owner, anchor_day=5, billing_from=today)
    result = generate_missing_charges(sub, today)
    assert result["created"] == 1
    assert Charge.objects.filter(subscription=sub, due_date=date(2026, 2, 5)).exists()
    assert generate_missing_charges(sub, date(2026, 2, 23))["created"] == 1
    assert Charge.objects.filter(subscription=sub).count() == 2
    assert Charge.objects.filter(subscription=sub).count() == 2
    second = generate_missing_charges(sub, today)
    assert second["created"] == 0


@pytest.mark.django_db
def test_trial_skips_until_trial_end(owner):
    today = date(2026, 1, 10)
    sub = _plan(
        owner,
        trial_end_date=date(2026, 1, 20),
        status=SubscriptionStatus.TRIAL,
        billing_from=date(2026, 1, 5),
    )
    assert generate_missing_charges(sub, today)["created"] == 0


@pytest.mark.django_db
def test_usd_round_half_up(owner):
    today = date(2026, 2, 5)
    sub = _plan(
        owner,
        currency=Currency.USD,
        anchor_day=5,
        billing_from=date(2026, 1, 5),
        start_date=date(2026, 1, 5),
    )
    PriceChange.objects.filter(subscription=sub).update(amount=Decimal("5.99"))
    ExchangeRate.objects.create(user=owner, rate_date=date(2026, 1, 1), usd_to_bdt=Decimal("122.5000"))
    generate_missing_charges(sub, today)
    charge = Charge.objects.get(subscription=sub, due_date=date(2026, 2, 5))
    assert charge.amount_bdt == Decimal("733.78")


@pytest.mark.django_db
def test_price_change_refreshes_unlocked_only(owner):
    today = date(2026, 1, 1)
    sub = _plan(owner, billing_from=date(2026, 1, 5))
    generate_missing_charges(sub, date(2026, 1, 26))
    upcoming = Charge.objects.get(subscription=sub, due_date=date(2026, 2, 5))
    PriceChange.objects.create(
        subscription=sub, amount=Decimal("150.00"), currency=Currency.BDT, effective_from=date(2026, 2, 1)
    )
    assert refresh_unlocked_charges(sub, date(2026, 1, 26)) == 1
    upcoming.refresh_from_db()
    assert upcoming.amount == Decimal("150.00")


@pytest.mark.django_db
def test_lock_due_charges(owner):
    sub = _plan(owner, billing_from=date(2026, 5, 1))
    generate_missing_charges(sub, date(2026, 5, 1))
    today = date(2026, 5, 26)
    generate_missing_charges(sub, today)
    lock_due_charges(date(2026, 5, 6))
    past = Charge.objects.get(subscription=sub, due_date=date(2026, 5, 5))
    assert past.locked is True
    future = Charge.objects.get(subscription=sub, due_date=date(2026, 6, 5))
    assert future.locked is False
    lock_due_charges(date(2026, 5, 1))
    assert lock_due_charges(date(2026, 6, 4)) == 0
    future.refresh_from_db()
    assert future.locked is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status",
    [
        SubscriptionStatus.PAUSED,
        SubscriptionStatus.CANCELLED,
        SubscriptionStatus.EXPIRED,
    ],
)
def test_inactive_status_creates_no_charges(owner, status):
    sub = _plan(owner, status=status)
    assert generate_missing_charges(sub, date(2026, 3, 1))["created"] == 0


@pytest.mark.django_db
def test_archived_plan_creates_no_charges(owner):
    sub = _plan(owner)
    sub.archived_on = timezone.now()
    sub.save(update_fields=["archived_on"])
    assert generate_missing_charges(sub, date(2026, 3, 1))["created"] == 0


@pytest.mark.django_db
def test_fixed_term_end_excludes_final_charge(owner):
    today = date(2026, 10, 26)
    sub = _plan(
        owner,
        start_date=date(2026, 9, 5),
        anchor_day=5,
        billing_from=today,
        renewal_type=RenewalType.FIXED_TERM,
        end_date=date(2026, 12, 5),
    )
    generate_missing_charges(sub, today)
    dates = list(Charge.objects.filter(subscription=sub).values_list("due_date", flat=True))
    assert dates == [date(2026, 11, 5)]


@pytest.mark.django_db
def test_billing_from_skips_back_charges(owner):
    today = date(2026, 9, 26)
    sub = _plan(
        owner,
        start_date=date(2025, 1, 5),
        billing_from=date(2026, 9, 5),
        anchor_day=5,
    )
    generate_missing_charges(sub, today)
    dates = list(Charge.objects.filter(subscription=sub).order_by("due_date").values_list("due_date", flat=True))
    assert all(d >= today for d in dates)
    assert date(2026, 10, 5) in dates


@pytest.mark.django_db
def test_resume_does_not_backfill_paused_cycles(owner):
    sub = _plan(owner, billing_from=date(2026, 1, 5))
    generate_missing_charges(sub, date(2026, 2, 23))
    with patch("plans.services.today_dhaka", return_value=date(2026, 4, 1)):
        plan_services.pause_subscription(owner, sub.pk)
    assert generate_missing_charges(sub, date(2026, 8, 1))["created"] == 0
    with patch("plans.services.today_dhaka", return_value=date(2026, 9, 1)):
        plan_services.resume_subscription(owner, sub.pk)
    sub.refresh_from_db()
    generate_missing_charges(sub, date(2026, 9, 15))
    dates = set(Charge.objects.filter(subscription=sub).values_list("due_date", flat=True))
    for skipped in (
        date(2026, 4, 5),
        date(2026, 5, 5),
        date(2026, 6, 5),
        date(2026, 7, 5),
        date(2026, 8, 5),
    ):
        assert skipped not in dates
    assert any(d >= date(2026, 9, 5) for d in dates)
    assert date(2026, 3, 5) in dates


@pytest.mark.django_db
def test_cancel_stops_charges_on_and_after_cancelled_on(owner):
    sub = _plan(owner, billing_from=date(2026, 1, 5))
    with patch("plans.services.today_dhaka", return_value=date(2026, 3, 1)):
        plan_services.cancel_subscription(owner, sub.pk)
    sub.refresh_from_db()
    generate_missing_charges(sub, date(2026, 6, 15))
    assert not Charge.objects.filter(subscription=sub, due_date__gte=sub.cancelled_on).exists()


@pytest.mark.django_db
def test_trial_charge_on_trial_end_when_active(owner):
    sub = _plan(
        owner,
        trial_end_date=date(2026, 1, 20),
        status=SubscriptionStatus.TRIAL,
        billing_from=date(2026, 1, 5),
        start_date=date(2026, 1, 5),
        anchor_day=20,
    )
    assert generate_missing_charges(sub, date(2026, 1, 12))["created"] == 0
    activate_ended_trials(date(2026, 1, 20))
    sub.refresh_from_db()
    assert sub.status == SubscriptionStatus.ACTIVE
    result = generate_missing_charges(sub, date(2026, 1, 20))
    assert result["created"] == 1
    assert Charge.objects.filter(subscription=sub, due_date=date(2026, 1, 20)).count() == 1


@pytest.mark.django_db
def test_usd_without_rate_skipped_other_plan_still_charges(owner):
    bdt = _plan(owner, plan_name="BDT ok", billing_from=date(2026, 1, 5))
    usd = _plan(
        owner,
        plan_name="USD skip",
        currency=Currency.USD,
        billing_from=date(2026, 1, 5),
    )
    totals = generate_charges_for_all_plans(date(2026, 1, 26))
    assert totals["errors"] >= 1
    assert Charge.objects.filter(subscription=bdt).exists()
    assert not Charge.objects.filter(subscription=usd).exists()


@pytest.mark.django_db
def test_price_change_does_not_alter_locked_past_charge(owner):
    sub = _plan(owner, billing_from=date(2026, 2, 24))
    generate_missing_charges(sub, date(2026, 2, 24))
    today = date(2026, 3, 6)
    lock_due_charges(today)
    generate_missing_charges(sub, today)
    jan = Charge.objects.get(subscription=sub, due_date=date(2026, 3, 5))
    assert jan.amount == Decimal("100.00")
    PriceChange.objects.create(
        subscription=sub,
        amount=Decimal("200.00"),
        currency=Currency.BDT,
        effective_from=date(2026, 2, 1),
    )
    refresh_unlocked_charges(sub, date(2026, 1, 26))
    jan.refresh_from_db()
    assert jan.amount == Decimal("100.00")
    assert jan.locked is True
