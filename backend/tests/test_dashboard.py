"""Dashboard summary and forecast API."""

from datetime import date
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.models import Category, ServiceName
from core.choices import Currency
from core.dates import today_dhaka
from dues.models import Due, DueStatus
from payments.models import Payment, ReviewStatus
from plans.models import CycleUnit, ExchangeRate, PlanMode, PriceChange, RenewalType, Subscription, SubscriptionStatus
from sharing.models import Invite, InviteStatus, Member, MemberStatus, SharedPlan, SplitType
from tests.test_billing_generator import _plan
from tests.test_subscriptions import WORLD_PASS, assert_error_shape, client_for, plan_payload


@pytest.mark.django_db
def test_dashboard_summary_anonymous_401():
    assert APIClient().get("/api/dashboard/summary/").status_code == 401


@pytest.mark.django_db
def test_dashboard_forecast_anonymous_401():
    assert APIClient().get("/api/dashboard/forecast/").status_code == 401


@pytest.mark.django_db
def test_dashboard_bad_month_400(world):
    r = client_for(world["owner"]).get("/api/dashboard/summary/?month=not-a-month")
    assert r.status_code == 400
    assert_error_shape(r)


@pytest.mark.django_db
def test_dashboard_bad_forecast_months_400(world):
    r = client_for(world["owner"]).get("/api/dashboard/forecast/?months=0")
    assert r.status_code == 400
    assert_error_shape(r)
    r2 = client_for(world["owner"]).get("/api/dashboard/forecast/?months=13")
    assert r2.status_code == 400


@pytest.mark.django_db
def test_dashboard_summary_shape(world):
    PriceChange.objects.get_or_create(
        subscription=world["plan_x"],
        effective_from=world["plan_x"].start_date,
        defaults={"amount": Decimal("900.00"), "currency": world["plan_x"].currency},
    )
    r = client_for(world["owner"]).get("/api/dashboard/summary/")
    assert r.status_code == 200
    data = r.json()
    for key in (
        "first_name",
        "month",
        "spend",
        "due_soon",
        "rarely",
        "attention",
        "next7",
        "by_category",
        "counts",
    ):
        assert key in data
    assert "total" in data["spend"] and "rows" in data["spend"]
    assert "owned_plans" in data["counts"]


@pytest.mark.django_db
def test_dashboard_spend_owner_shared_seat(world):
    sub = world["plan_x"]
    PriceChange.objects.get_or_create(
        subscription=sub,
        effective_from=sub.start_date,
        defaults={"amount": Decimal("900.00"), "currency": sub.currency},
    )
    month = sub.start_date.strftime("%Y-%m")
    rows = client_for(world["owner"]).get(f"/api/dashboard/summary/?month={month}").json()["spend"]["rows"]
    owner_rows = [r for r in rows if r["plan_id"] == sub.pk and r["role"] == "owner"]
    assert owner_rows
    assert Decimal(owner_rows[0]["amount"]) < Decimal("900.00")


@pytest.mark.django_db
def test_dashboard_spend_member(world):
    sub = world["plan_x"]
    PriceChange.objects.get_or_create(
        subscription=sub,
        effective_from=sub.start_date,
        defaults={"amount": Decimal("900.00"), "currency": sub.currency},
    )
    month = sub.start_date.strftime("%Y-%m")
    data = client_for(world["member"]).get(f"/api/dashboard/summary/?month={month}").json()
    member_rows = [r for r in data["spend"]["rows"] if r["role"] == "member"]
    assert member_rows
    assert Decimal(data["spend"]["joined"]) > 0


@pytest.mark.django_db
def test_dashboard_reseller_owner_zero(db):
    from django.contrib.auth import get_user_model

    owner = get_user_model().objects.create_user(
        email="resell@example.com", password=WORLD_PASS, name="Resell", email_verified=True
    )
    client = client_for(owner)
    streaming = Category.objects.get(is_preset=True, name="Streaming")
    sn = ServiceName.objects.filter(is_preset=True, category=streaming).first()
    sub = Subscription.objects.create(
        owner=owner,
        service_name=sn,
        category=streaming,
        plan_name="Reseller",
        plan_mode=PlanMode.RESELLER,
        currency=Currency.BDT,
        cycle_unit=CycleUnit.MONTH,
        cycle_count=1,
        anchor_day=5,
        start_date=date(2026, 2, 5),
        renewal_type=RenewalType.AUTO,
        status=SubscriptionStatus.ACTIVE,
        billing_from=date(2026, 2, 5),
        recommended_method="bkash",
    )
    PriceChange.objects.create(subscription=sub, amount=Decimal("500.00"), currency=Currency.BDT, effective_from=sub.start_date)
    month = "2026-02"
    data = client.get(f"/api/dashboard/summary/?month={month}").json()
    assert Decimal(data["spend"]["owned"]) == 0


@pytest.mark.django_db
def test_dashboard_excludes_archived(world):
    world["plan_x"].archived_on = timezone.now()
    world["plan_x"].save(update_fields=["archived_on"])
    counts = client_for(world["owner"]).get("/api/dashboard/summary/").json()["counts"]
    assert counts["owned_plans"] == 0


@pytest.mark.django_db
def test_dashboard_forecast_kinds_yearly_and_this(monkeypatch):
    from django.contrib.auth import get_user_model

    owner = get_user_model().objects.create_user(
        email="yr@example.com", password=WORLD_PASS, name="Year", email_verified=True
    )
    _plan(owner, cycle_unit=CycleUnit.YEAR, cycle_count=1, start_date=date(2025, 2, 5), billing_from=date(2025, 2, 5))
    monkeypatch.setattr("reports.views.today_dhaka", lambda: date(2026, 2, 1))
    rows = client_for(owner).get("/api/dashboard/forecast/?months=3").json()
    assert rows[0]["kind"] == "yearly"
    if len(rows) > 1:
        assert rows[1]["kind"] == "regular"


@pytest.mark.django_db
def test_dashboard_scoped_to_user(world):
    PriceChange.objects.get_or_create(
        subscription=world["plan_x"],
        effective_from=world["plan_x"].start_date,
        defaults={"amount": Decimal("900.00"), "currency": world["plan_x"].currency},
    )
    o = client_for(world["owner"]).get("/api/dashboard/summary/").json()["spend"]["total"]
    out = client_for(world["outsider"]).get("/api/dashboard/summary/").json()["spend"]["total"]
    assert Decimal(o) > Decimal(out)


@pytest.mark.django_db
def test_dashboard_attention_review(world):
    from tests.test_subscriptions import make_payment

    make_payment(world["shared_x"], world["member_row"], world["member"], ReviewStatus.PENDING)
    items = client_for(world["owner"]).get("/api/dashboard/summary/").json()["attention"]
    assert any(i["kind"] == "review" for i in items)


@pytest.mark.django_db
def test_dashboard_constant_query_count(world):
    PriceChange.objects.get_or_create(
        subscription=world["plan_x"],
        effective_from=world["plan_x"].start_date,
        defaults={"amount": Decimal("900.00"), "currency": world["plan_x"].currency},
    )
    owner = client_for(world["owner"])

    def count():
        with CaptureQueriesContext(connection) as ctx:
            r = owner.get("/api/dashboard/summary/")
            assert r.status_code == 200
        return len(ctx)

    base = count()
    for i in range(9):
        owner.post(
            "/api/subscriptions/",
            {**plan_payload(plan_name=f"Dash extra {i}"), "seats": 1},
            format="json",
        )
    assert count() == base
