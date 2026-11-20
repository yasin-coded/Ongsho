"""billing_from and no back-charges (lead window uses TODAY = 2026-11-15 baseline)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from billing.models import Charge
from billing.services import generate_missing_charges
from billing.services import activate_ended_trials
from dues.models import Due, DueStatus
from jobs.services import run_daily
from plans import services as plan_services
from plans.models import CycleUnit, PlanMode, RenewalType, Subscription, SubscriptionStatus
from tests.test_billing_generator import _plan
from tests.test_subscriptions import client_for, plan_payload

User = get_user_model()
WORLD_PASS = "pass12345"
T0 = date(2026, 11, 15)


@pytest.fixture
def owner(db):
    return User.objects.create_user(
        email="bf@example.com", password=WORLD_PASS, name="Bf", email_verified=True
    )


@pytest.fixture
def today_dhaka_t0():
    with patch("core.dates.today_dhaka", return_value=T0):
        with patch("plans.services.today_dhaka", return_value=T0):
            yield T0


@pytest.mark.django_db
def test_old_start_no_back_charge_until_lead(owner, today_dhaka_t0):
    sub = _plan(
        owner,
        start_date=date(2025, 2, 5),
        billing_from=T0,
        anchor_day=5,
    )
    generate_missing_charges(sub, T0)
    dates = list(Charge.objects.filter(subscription=sub).values_list("due_date", flat=True))
    assert all(d >= T0 for d in dates)
    assert date(2026, 12, 5) not in dates
    generate_missing_charges(sub, date(2026, 11, 26))
    assert Charge.objects.filter(subscription=sub, due_date=date(2026, 12, 5)).exists()


@pytest.mark.django_db
def test_create_with_next_renewal_sets_billing_from(owner, today_dhaka_t0):
    client = client_for(owner)
    nr = date(2026, 12, 5)
    r = client.post(
        "/api/subscriptions/",
        {
            **plan_payload(start_date=str(date(2025, 2, 5))),
            "next_renewal_date": str(nr),
        },
        format="json",
    )
    assert r.status_code == 201
    sub = Subscription.objects.get(pk=r.json()["id"])
    assert sub.billing_from == nr
    assert sub.anchor_day == 5
    generate_missing_charges(sub, T0)
    assert not Charge.objects.filter(subscription=sub, due_date__lt=T0).exists()
    generate_missing_charges(sub, date(2026, 11, 26))
    assert Charge.objects.filter(subscription=sub, due_date=nr).exists()


@pytest.mark.django_db
def test_recent_start_first_due_not_created_until_lead(owner, today_dhaka_t0):
    sub = _plan(owner, start_date=date(2026, 11, 10), billing_from=T0, anchor_day=10)
    generate_missing_charges(sub, T0)
    assert not Charge.objects.filter(subscription=sub).exists()


@pytest.mark.django_db
def test_prior_cycle_in_lead_creates_owner_due(owner, today_dhaka_t0):
    client = client_for(owner)
    r = client.post(
        "/api/subscriptions/",
        {**plan_payload(plan_name="In lead", start_date=str(date(2026, 10, 20))), "seats": 2},
        format="json",
    )
    assert r.status_code == 201
    sub = Subscription.objects.get(pk=r.json()["id"])
    assert sub.billing_from == T0
    generate_missing_charges(sub, T0)
    ch = Charge.objects.get(subscription=sub, due_date=date(2026, 11, 20))
    from sharing.models import SharedPlan

    shared = SharedPlan.objects.get(subscription=sub)
    owner_due = Due.objects.get(charge=ch, member__user=owner)
    assert owner_due.status == DueStatus.DUE


@pytest.mark.django_db
def test_yearly_nothing_until_lead(owner, today_dhaka_t0):
    sub = _plan(
        owner,
        cycle_unit=CycleUnit.YEAR,
        cycle_count=1,
        start_date=date(2025, 12, 20),
        billing_from=T0,
        anchor_day=20,
    )
    generate_missing_charges(sub, T0)
    assert not Charge.objects.filter(subscription=sub, due_date=date(2026, 12, 20)).exists()


@pytest.mark.django_db
def test_trial_charge_only_in_window_when_active(owner, today_dhaka_t0):
    sub = _plan(
        owner,
        start_date=date(2026, 11, 1),
        trial_end_date=date(2026, 11, 18),
        status=SubscriptionStatus.TRIAL,
        billing_from=T0,
        anchor_day=18,
    )
    assert generate_missing_charges(sub, T0)["created"] == 0
    assert generate_missing_charges(sub, date(2026, 11, 9))["created"] == 0
    activate_ended_trials(date(2026, 11, 18))
    sub.refresh_from_db()
    assert sub.status == SubscriptionStatus.ACTIVE
    generate_missing_charges(sub, date(2026, 11, 9))
    assert Charge.objects.filter(subscription=sub, due_date=date(2026, 11, 18)).exists()


@pytest.mark.django_db
def test_patch_next_renewal_voids_and_sets_billing_from(owner, today_dhaka_t0):
    sub = _plan(
        owner,
        start_date=date(2025, 6, 5),
        billing_from=T0,
        anchor_day=5,
    )
    generate_missing_charges(sub, date(2026, 11, 26))
    old = Charge.objects.filter(subscription=sub, due_date=date(2026, 12, 5)).first()
    assert old
    from billing.selectors import schedule_for_subscription
    from core.schedule import next_due_date, validate_next_renewal

    sched = schedule_for_subscription(sub)
    patch_today = date(2026, 12, 6)
    target = next_due_date(sched, patch_today)
    assert target is not None
    assert validate_next_renewal(sched, target, patch_today)
    with patch("plans.services.today_dhaka", return_value=patch_today):
        plan_services.apply_next_renewal_date(owner, sub.pk, target)
    sub.refresh_from_db()
    assert sub.billing_from == target
    if target != date(2026, 12, 5):
        assert not Charge.objects.filter(subscription=sub, due_date=date(2026, 12, 5)).exists()
    generate_missing_charges(sub, date(2026, 12, 28))
    assert Charge.objects.filter(subscription=sub, due_date=target).exists()
    assert not Charge.objects.filter(subscription=sub, due_date__lt=target, due_date__gte=T0).exists()


@pytest.mark.django_db
def test_resume_no_gap_backfill_then_daily(owner, today_dhaka_t0):
    sub = _plan(owner, billing_from=date(2026, 2, 5), anchor_day=5)
    generate_missing_charges(sub, date(2026, 2, 23))
    with patch("plans.services.today_dhaka", return_value=date(2026, 4, 1)):
        plan_services.pause_subscription(owner, sub.pk)
    with patch("plans.services.today_dhaka", return_value=date(2026, 9, 1)):
        plan_services.resume_subscription(owner, sub.pk)
    sub.refresh_from_db()
    assert sub.billing_from == date(2026, 9, 1)
    generate_missing_charges(sub, date(2026, 9, 15))
    run_daily(date(2026, 9, 15))
    dates = set(Charge.objects.filter(subscription=sub).values_list("due_date", flat=True))
    for gap in (
        date(2026, 4, 5),
        date(2026, 5, 5),
        date(2026, 6, 5),
        date(2026, 7, 5),
        date(2026, 8, 5),
    ):
        assert gap not in dates
    assert any(d >= date(2026, 9, 5) for d in dates)