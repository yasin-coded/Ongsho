from datetime import date

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.models import Category, ServiceName
from core.choices import Currency, PaymentMethod
from core.dates import today_dhaka
from dues.models import Due, DueStatus
from plans.models import CycleUnit, PlanMode, PriceChange, RenewalType, Subscription, SubscriptionStatus
from sharing.models import Member, MemberStatus, SharedPlan, SplitType
from tests.test_subscriptions import assert_error_shape, client_for


@pytest.mark.django_db
def test_calendar_anonymous_401():
    response = APIClient().get("/api/calendar/")
    assert response.status_code == 401
    assert_error_shape(response)


@pytest.mark.django_db
def test_calendar_bad_month_400(world):
    response = client_for(world["owner"]).get("/api/calendar/?month=bad")
    assert response.status_code == 400


@pytest.mark.django_db
def test_calendar_owner_events_and_next7(world):
    from decimal import Decimal
    from plans.models import PriceChange

    PriceChange.objects.get_or_create(
        subscription=world["plan_x"],
        effective_from=world["plan_x"].start_date,
        defaults={
            "amount": Decimal("1000.00"),
            "currency": world["plan_x"].currency,
        },
    )
    client = client_for(world["owner"])
    month = today_dhaka().strftime("%Y-%m")
    data = client.get(f"/api/calendar/?month={month}").json()
    assert "events" in data and "next7" in data
    owner_events = [e for e in data["events"] if e["role"] == "owner" and e["plan_id"] == world["plan_x"].pk]
    assert owner_events
    assert all(e["kind"] in ("renews", "trial_end", "expires") for e in owner_events)


@pytest.mark.django_db
def test_calendar_member_event(world):
    from decimal import Decimal
    from plans.models import PriceChange

    shared = world["shared_x"]
    sub = shared.subscription
    PriceChange.objects.get_or_create(
        subscription=sub,
        effective_from=sub.start_date,
        defaults={"amount": Decimal("1000.00"), "currency": sub.currency},
    )
    client = client_for(world["member"])
    month = world["charge_x"].due_date.strftime("%Y-%m")
    events = client.get(f"/api/calendar/?month={month}").json()["events"]
    member_rows = [e for e in events if e["role"] == "member" and e["plan_id"] == sub.pk]
    assert member_rows
    assert member_rows[0]["kind"] == "due"
    assert member_rows[0]["status"] in ("due", DueStatus.DUE)


@pytest.mark.django_db
def test_calendar_hides_archived(world):
    world["plan_x"].archived_on = timezone.now()
    world["plan_x"].save(update_fields=["archived_on"])
    month = today_dhaka().strftime("%Y-%m")
    events = client_for(world["owner"]).get(f"/api/calendar/?month={month}").json()["events"]
    assert not any(e["plan_id"] == world["plan_x"].pk for e in events)


@pytest.mark.django_db
def test_calendar_billing_from_past_renewal_shows():
    from django.contrib.auth import get_user_model

    from billing.selectors import calendar_events
    from tests.test_billing_generator import _plan
    from tests.test_subscriptions import WORLD_PASS

    owner = get_user_model().objects.create_user(
        email="calbf@example.com", password=WORLD_PASS, name="Cal", email_verified=True
    )
    today = date(2026, 11, 15)
    sub = _plan(owner, start_date=date(2026, 1, 13), billing_from=date(2026, 11, 13), anchor_day=13)
    events = calendar_events(owner, today=today, month_start=date(2026, 11, 1))
    dates = [e["date"] for e in events if e["plan_id"] == sub.pk]
    assert "2026-11-13" in dates


@pytest.mark.django_db
def test_calendar_billing_from_skips_future_before_anchor():
    from django.contrib.auth import get_user_model

    from billing.selectors import calendar_events
    from tests.test_billing_generator import _plan
    from tests.test_subscriptions import WORLD_PASS

    owner = get_user_model().objects.create_user(
        email="calfut@example.com", password=WORLD_PASS, name="CalFut", email_verified=True
    )
    today = date(2026, 2, 1)
    sub = _plan(owner, start_date=date(2026, 1, 5), billing_from=date(2026, 3, 5), anchor_day=5)
    events = calendar_events(owner, today=today, month_start=date(2026, 2, 1))
    owner_dates = [e["date"] for e in events if e["plan_id"] == sub.pk and e["role"] == "owner"]
    assert "2026-02-05" not in owner_dates
