"""Dashboard summary/forecast coverage (additive)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from billing import services as billing_services
from billing.models import Charge, ChargeStatus
from core.choices import Currency, PaymentMethod
from core.dates import today_dhaka
from dues.models import Due, DueStatus
from notifications.models import Notification
from payments.models import Payment, PaymentAllocation, ReviewStatus
from plans.models import CycleUnit, ExchangeRate, PlanMode, PriceChange, RenewalType, SubscriptionStatus
from reports import selectors as report_selectors
from sharing.models import Invite, InviteStatus, Member, MemberStatus, OwnershipTransfer, SharedPlan, SplitType, TransferStatus

from tests.test_billing_generator import _plan
from tests.test_subscriptions import WORLD_PASS, client_for, plan_payload

User = get_user_model()


@pytest.fixture
def dash_owner(db):
    return User.objects.create_user(
        email="dash@example.com", password=WORLD_PASS, name="Dash", email_verified=True
    )


def _summary(client, month=None):
    url = "/api/dashboard/summary/"
    if month:
        url += f"?month={month}"
    return client.get(url)


def _forecast(client, months=12):
    return client.get(f"/api/dashboard/forecast/?months={months}")


@pytest.mark.django_db
def test_dashboard_solo_owner_plan_spend(dash_owner):
    today = date(2026, 4, 10)
    sub = _plan(dash_owner, start_date=date(2026, 3, 5), billing_from=date(2026, 3, 5), anchor_day=5)
    assert not SharedPlan.objects.filter(subscription=sub).exists()
    data = report_selectors.dashboard_summary(dash_owner, month=date(2026, 4, 1), today=today)
    assert data["counts"]["owned_plans"] == 1
    owner_rows = [r for r in data["spend"]["rows"] if r["role"] == "owner" and r["plan_id"] == sub.pk]
    assert owner_rows
    assert Decimal(owner_rows[0]["amount"]) == Decimal("100.00")


@pytest.mark.django_db
def test_dashboard_usd_plan_bdt_spend(dash_owner):
    today = date(2026, 5, 10)
    sub = _plan(
        dash_owner,
        currency=Currency.USD,
        start_date=date(2026, 4, 5),
        billing_from=date(2026, 4, 5),
        anchor_day=5,
    )
    PriceChange.objects.filter(subscription=sub).update(amount=Decimal("10.00"), currency=Currency.USD)
    ExchangeRate.objects.create(
        user=dash_owner, rate_date=date(2026, 4, 1), usd_to_bdt=Decimal("122.0000"), source="manual"
    )
    data = report_selectors.dashboard_summary(dash_owner, month=date(2026, 5, 1), today=today)
    owner_rows = [r for r in data["spend"]["rows"] if r["plan_id"] == sub.pk]
    assert owner_rows
    assert Decimal(owner_rows[0]["amount"]) == Decimal("1220.00")


@pytest.mark.django_db
def test_dashboard_billing_from_respected(dash_owner):
    today = date(2026, 2, 15)
    sub = _plan(
        dash_owner,
        start_date=date(2026, 1, 5),
        billing_from=date(2026, 3, 5),
        anchor_day=5,
    )
    feb = report_selectors.dashboard_summary(dash_owner, month=date(2026, 2, 1), today=today)
    feb_rows = [r for r in feb["spend"]["rows"] if r["plan_id"] == sub.pk]
    assert len(feb_rows) == 1
    assert feb_rows[0]["date"] == "2026-02-05"
    jan = report_selectors.dashboard_summary(dash_owner, month=date(2026, 1, 1), today=today)
    assert not any(r["plan_id"] == sub.pk for r in jan["spend"]["rows"])
    march = report_selectors.dashboard_summary(dash_owner, month=date(2026, 3, 1), today=today)
    mar_rows = [r for r in march["spend"]["rows"] if r["plan_id"] == sub.pk]
    assert len(mar_rows) == 1
    assert mar_rows[0]["date"] == "2026-03-05"


@pytest.mark.django_db
def test_dashboard_rarely_used_yearly_cost(dash_owner):
    today = date(2026, 5, 15)
    sub = _plan(
        dash_owner,
        plan_name="Rare Year",
        rarely_used=True,
        cycle_unit=CycleUnit.YEAR,
        cycle_count=1,
        start_date=date(2026, 1, 1),
        billing_from=date(2026, 1, 1),
        anchor_day=1,
    )
    PriceChange.objects.filter(subscription=sub).update(amount=Decimal("1200.00"))
    Charge.objects.create(
        subscription=sub,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        due_date=date(2026, 1, 1),
        amount=Decimal("1200.00"),
        amount_bdt=Decimal("1200.00"),
        currency=Currency.BDT,
        status=ChargeStatus.DUE,
        locked=True,
    )
    data = report_selectors.dashboard_summary(dash_owner, month=date(2026, 5, 1), today=today)
    assert any(p["id"] == sub.pk for p in data["rarely"]["plans"])
    assert Decimal(data["rarely"]["yearly"]) == Decimal("1200.00")


@pytest.mark.django_db
def test_dashboard_attention_all_kinds(dash_owner, db):
    reviewer_client = client_for(dash_owner)
    today = today_dhaka()
    from tests.test_billing_generator import month_before

    r = reviewer_client.post(
        "/api/subscriptions/",
        {**plan_payload(plan_name="Attn Plan", start_date=str(month_before(today))), "seats": 2},
        format="json",
    )
    assert r.status_code == 201
    plan_id = r.json()["id"]
    shared = SharedPlan.objects.get(subscription_id=plan_id)

    member_user = User.objects.create_user(
        email="duepayer@example.com", password=WORLD_PASS, name="Payer", email_verified=True
    )
    member_row = Member.objects.create(
        shared_plan=shared,
        user=member_user,
        share_type=SplitType.EQUAL,
        status=MemberStatus.ACTIVE,
        joined_on=date(2026, 2, 5),
    )
    charge = Charge.objects.filter(subscription=shared.subscription).order_by("-due_date").first()
    if charge is None:
        billing_services.generate_missing_charges(shared.subscription, today)
        charge = Charge.objects.filter(subscription=shared.subscription).order_by("-due_date").first()
    assert charge
    due, _ = Due.objects.get_or_create(
        charge=charge,
        member=member_row,
        defaults={"amount_bdt": Decimal("50.00"), "status": DueStatus.DUE},
    )
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    pay = Payment.objects.create(
        shared_plan=shared,
        member=member_row,
        recorded_by=member_user,
        method=PaymentMethod.BKASH,
        amount=due.amount_bdt,
        transaction_id="ATNREVW1",
        review_status=ReviewStatus.PENDING,
    )
    PaymentAllocation.objects.create(payment=pay, due=due, amount_applied=due.amount_bdt)
    due.status = DueStatus.PENDING
    due.save(update_fields=["status"])

    leave_user = User.objects.create_user(
        email="leaver@example.com", password=WORLD_PASS, name="Leaver", email_verified=True
    )
    Member.objects.create(
        shared_plan=shared,
        user=leave_user,
        share_type=SplitType.EQUAL,
        status=MemberStatus.LEAVE_REQUESTED,
        joined_on=date(2026, 2, 5),
    )

    invitee = User.objects.create_user(
        email="invitee@example.com", password=WORLD_PASS, name="Inv", email_verified=True
    )
    Invite.objects.create(
        shared_plan=shared,
        invited_by=dash_owner,
        email=invitee.email,
        token_hash="unique-token-hash-attn-invite",
        expires_on=timezone.now() + timedelta(days=5),
        status=InviteStatus.PENDING,
    )

    transferee = User.objects.create_user(
        email="newowner@example.com", password=WORLD_PASS, name="New", email_verified=True
    )
    OwnershipTransfer.objects.create(
        shared_plan=shared,
        from_user=dash_owner,
        to_user=transferee,
        status=TransferStatus.PENDING,
    )

    owner_attn = report_selectors.dashboard_summary(dash_owner, month=today.replace(day=1), today=today)["attention"]
    kinds = {i["kind"] for i in owner_attn}
    assert {"review", "leave"} <= kinds

    invitee_kinds = {
        i["kind"]
        for i in report_selectors.dashboard_summary(invitee, month=today.replace(day=1), today=today)["attention"]
    }
    assert "invite" in invitee_kinds
    assert "transfer" in {i["kind"] for i in report_selectors.dashboard_summary(transferee, month=today.replace(day=1), today=today)["attention"]}


@pytest.mark.django_db
def test_dashboard_paused_cancelled_excluded(dash_owner):
    today = date(2026, 7, 15)
    active = _plan(dash_owner, plan_name="Active One", start_date=date(2026, 6, 5), billing_from=date(2026, 6, 5), anchor_day=5)
    _plan(
        dash_owner,
        plan_name="Paused One",
        status=SubscriptionStatus.PAUSED,
        paused_on=date(2026, 6, 1),
        start_date=date(2026, 1, 5),
        billing_from=date(2026, 1, 5),
        anchor_day=5,
    )
    _plan(
        dash_owner,
        plan_name="Cancelled One",
        status=SubscriptionStatus.CANCELLED,
        cancelled_on=date(2026, 6, 10),
        start_date=date(2026, 1, 5),
        billing_from=date(2026, 1, 5),
        anchor_day=5,
    )
    data = report_selectors.dashboard_summary(dash_owner, month=date(2026, 7, 1), today=today)
    assert data["counts"]["owned_plans"] == 1
    plan_ids = {r["plan_id"] for r in data["spend"]["rows"]}
    assert active.pk in plan_ids
    assert not any(name in {r["plan_name"] for r in data["spend"]["rows"]} for name in ("Paused One", "Cancelled One"))


@pytest.mark.django_db
def test_dashboard_due_soon_lists_upcoming(dash_owner):
    today = date(2026, 7, 10)
    renewal = today + timedelta(days=3)
    from tests.test_billing_generator import month_before

    start = month_before(renewal)
    sub = _plan(
        dash_owner,
        plan_name="Due Soon",
        start_date=start,
        billing_from=start,
        anchor_day=renewal.day,
    )
    body = report_selectors.dashboard_summary(dash_owner, month=date(2026, 7, 1), today=today)
    assert body["due_soon"]["count"] >= 1
    assert any(i["plan_id"] == sub.pk for i in body["due_soon"]["items"])


@pytest.mark.django_db
def test_dashboard_forecast_marks_yearly_plan(dash_owner):
    today = date(2026, 8, 10)
    sub = _plan(
        dash_owner,
        plan_name="Yearly FC",
        cycle_unit=CycleUnit.YEAR,
        cycle_count=1,
        start_date=date(2025, 8, 5),
        billing_from=date(2025, 8, 5),
        anchor_day=5,
    )
    rows = report_selectors.dashboard_forecast(dash_owner, months=3, today=today)
    hit = next((r for r in rows if r["key"] == "2026-08"), None)
    assert hit is not None
    assert hit["kind"] == "yearly"
    assert sub.plan_name in hit["yearly_plans"]


@pytest.mark.django_db
def test_dashboard_forecast_query_count_stable_with_ten_plans(dash_owner):
    today = date(2026, 9, 12)

    def count_forecast_queries():
        with CaptureQueriesContext(connection) as ctx:
            report_selectors.dashboard_forecast(dash_owner, months=12, today=today)
        return len(ctx.captured_queries)

    _plan(dash_owner, plan_name="FC0", start_date=date(2026, 1, 5), billing_from=date(2026, 1, 5), anchor_day=5)
    one = count_forecast_queries()
    for i in range(1, 10):
        _plan(
            dash_owner,
            plan_name=f"FC{i}",
            start_date=date(2026, 1, 5),
            billing_from=date(2026, 1, 5),
            anchor_day=5,
        )
    ten = count_forecast_queries()
    assert ten == one


@pytest.mark.django_db
def test_dashboard_billing_from_old_start_passed_renewal_in_month(dash_owner):
    """Plan added with old start: already-passed renewal this month counts in spend."""
    today = date(2026, 11, 13)
    sub = _plan(
        dash_owner,
        start_date=date(2026, 1, 13),
        billing_from=today,
        anchor_day=13,
    )
    data = report_selectors.dashboard_summary(dash_owner, month=date(2026, 11, 1), today=today)
    rows = [r for r in data["spend"]["rows"] if r["plan_id"] == sub.pk]
    assert any(r["date"] == "2026-11-13" for r in rows)
    assert Decimal(data["spend"]["owned"]) >= Decimal("100.00")


@pytest.mark.django_db
def test_dashboard_billing_from_hides_future_before_anchor(dash_owner):
    today = date(2026, 2, 1)
    sub = _plan(
        dash_owner,
        start_date=date(2026, 1, 5),
        billing_from=date(2026, 3, 5),
        anchor_day=5,
    )
    data = report_selectors.dashboard_summary(dash_owner, month=date(2026, 2, 1), today=today)
    assert not any(r["plan_id"] == sub.pk and r["date"] == "2026-02-05" for r in data["spend"]["rows"])
    body = report_selectors.dashboard_summary(dash_owner, month=date(2026, 2, 1), today=today)
    assert not any(i["plan_id"] == sub.pk for i in body["next7"])


@pytest.mark.django_db
def test_dashboard_billing_from_next_renewal_no_phantom_between(dash_owner):
    """Next-renewal / billing_from at Mar 5: Feb 5 must not appear while it is still in the future."""
    today = date(2026, 2, 1)
    sub = _plan(
        dash_owner,
        start_date=date(2026, 1, 5),
        billing_from=date(2026, 3, 5),
        anchor_day=5,
    )
    from billing.selectors import calendar_events

    events = calendar_events(dash_owner, today=today, month_start=date(2026, 2, 1))
    owner_dates = [e["date"] for e in events if e["plan_id"] == sub.pk and e["role"] == "owner"]
    assert "2026-02-05" not in owner_dates
    due = report_selectors.dashboard_summary(dash_owner, month=date(2026, 2, 1), today=today)["due_soon"]
    assert not any(i["plan_id"] == sub.pk for i in due["items"])
    later = report_selectors.dashboard_summary(dash_owner, month=date(2026, 2, 1), today=date(2026, 2, 15))
    assert any(r["plan_id"] == sub.pk and r["date"] == "2026-02-05" for r in later["spend"]["rows"])
