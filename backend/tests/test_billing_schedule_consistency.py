"""Schedule consistency: one source of truth in core.schedule across surfaces."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from core.dates import today_dhaka

from billing.selectors import schedule_for_subscription
from core.schedule import Schedule, due_dates_between, first_renewal_date, next_due_date, renewal_k_start
from notifications import reminders as reminder_services
from plans.selectors import display_next_renewal
from reports import selectors as report_selectors
from plans.models import CycleUnit, SubscriptionStatus
from tests.test_billing_generator import _plan

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        email="sched@example.com", password="pass12345", name="Sched", email_verified=True
    )


def _plan_schedules():
    cases = [
        dict(label="monthly-31", start=date(2026, 1, 31), anchor=31, unit="month", count=1, trial=None),
        dict(label="yearly-feb29", start=date(2028, 2, 29), anchor=29, unit="year", count=1, trial=None),
        dict(label="weekly", start=date(2026, 6, 3), anchor=3, unit="week", count=1, trial=None),
        dict(label="every-3-months", start=date(2026, 4, 10), anchor=10, unit="month", count=3, trial=None),
        dict(label="trial", start=date(2026, 5, 1), anchor=15, unit="month", count=1, trial=date(2026, 5, 15)),
        dict(
            label="fixed-term",
            start=date(2026, 7, 5),
            anchor=5,
            unit="month",
            count=1,
            trial=None,
            renewal_type="fixed_term",
            end_date=date(2026, 12, 5),
        ),
        dict(
            label="cancelled",
            start=date(2026, 8, 5),
            anchor=5,
            unit="month",
            count=1,
            trial=None,
            status="cancelled",
            cancelled_on=date(2026, 11, 5),
        ),
        dict(label="paused", start=date(2026, 9, 5), anchor=5, unit="month", count=1, trial=None, status="paused", paused_on=date(2026, 10, 1)),
        dict(
            label="next-renewal-on-today",
            start=date(2026, 1, 5),
            anchor=5,
            unit="month",
            count=1,
            trial=None,
        ),
    ]
    return cases


def _sub_from_spec(spec, owner):
    status_map = {
        "cancelled": SubscriptionStatus.CANCELLED,
        "paused": SubscriptionStatus.PAUSED,
    }
    extra = {
        k: status_map.get(v, v)
        for k, v in spec.items()
        if k in ("renewal_type", "end_date", "status", "cancelled_on", "paused_on")
    }
    return _plan(
        owner,
        start_date=spec["start"],
        anchor_day=spec["anchor"],
        cycle_unit=getattr(CycleUnit, spec["unit"].upper()),
        cycle_count=spec["count"],
        trial_end_date=spec.get("trial"),
        billing_from=spec["start"],
        **extra,
    )


def test_due_dates_never_include_plain_start(owner):
    for spec in _plan_schedules():
        sub = _plan(
            owner,
            start_date=spec["start"],
            anchor_day=spec["anchor"],
            cycle_unit=getattr(CycleUnit, spec["unit"].upper()),
            cycle_count=spec["count"],
            trial_end_date=spec.get("trial"),
            billing_from=spec["start"],
            **{
                k: (SubscriptionStatus.CANCELLED if v == "cancelled" else SubscriptionStatus.PAUSED if v == "paused" else v)
                for k, v in spec.items()
                if k in ("renewal_type", "end_date", "status", "cancelled_on", "paused_on")
            },
        )
        schedule = schedule_for_subscription(sub)
        grid_start = date(2026, 1, 1)
        grid_end = date(2027, 12, 31)
        dues = due_dates_between(schedule, grid_start, grid_end)
        assert sub.start_date not in dues or (sub.trial_end_date and sub.trial_end_date in dues), spec["label"]
        assert first_renewal_date(schedule) not in (sub.start_date,) or sub.trial_end_date is not None, spec["label"]


def test_next_renewal_matches_first_due_on_or_after_today(owner):
    today = date(2026, 11, 15)
    sub = _plan(owner, start_date=date(2026, 11, 5), billing_from=date(2026, 11, 5), anchor_day=5)
    schedule = schedule_for_subscription(sub)
    nxt = next_due_date(schedule, max(today, sub.billing_from))
    assert display_next_renewal(sub) == nxt.isoformat()
    assert nxt == date(2026, 12, 5)


def test_generator_calendar_dashboard_share_due_dates(owner):
    today = date(2026, 4, 20)
    sub = _plan(owner, start_date=date(2026, 1, 5), billing_from=date(2026, 1, 5), anchor_day=5)
    schedule = schedule_for_subscription(sub)
    schedule_dues = due_dates_between(schedule, sub.billing_from, today)
    spend = report_selectors.dashboard_summary(owner, month=date(2026, 4, 1), today=today)
    spend_dates = {r["date"] for r in spend["spend"]["rows"] if r["plan_id"] == sub.pk}
    for d in spend_dates:
        assert date.fromisoformat(d) in schedule_dues or date.fromisoformat(d) < today


def test_generator_due_dates_match_schedule_in_lead(owner):
    from billing.services import generate_missing_charges
    from billing.models import Charge

    today = date(2026, 11, 26)
    sub = _plan(
        owner,
        start_date=date(2025, 2, 5),
        billing_from=today,
        anchor_day=5,
    )
    schedule = schedule_for_subscription(sub)
    expected = [
        d
        for d in due_dates_between(schedule, sub.billing_from, today)
        if d <= today and d >= sub.billing_from
    ]
    generate_missing_charges(sub, today)
    got = list(Charge.objects.filter(subscription=sub).values_list("due_date", flat=True))
    for d in got:
        assert d in due_dates_between(schedule, date(2025, 1, 1), date(2027, 12, 31))
    if expected:
        assert max(expected) in got or all(g >= today for g in got)


@pytest.mark.parametrize("spec", _plan_schedules())
def test_table_rows_agree_on_display_next_renewal(spec, owner):
    sub = _sub_from_spec(spec, owner)
    if sub.status in (SubscriptionStatus.CANCELLED, SubscriptionStatus.PAUSED):
        pytest.skip(f"{spec['label']} — renewal not defined while {sub.status}")
    if sub.status == SubscriptionStatus.TRIAL and sub.trial_end_date:
        assert display_next_renewal(sub) == sub.trial_end_date.isoformat()
        return
    schedule = schedule_for_subscription(sub)
    floor = max(today_dhaka(), sub.billing_from)
    nxt = next_due_date(schedule, floor)
    shown = display_next_renewal(sub)
    assert shown == (nxt.isoformat() if nxt else None), spec["label"]


def test_live_surfaces_agree_on_renewal_day(owner):
    from billing.models import Charge
    from billing.services import generate_missing_charges
    from django.contrib.auth import get_user_model

    renewal_day = date(2026, 11, 5)
    sub = _plan(owner, start_date=date(2026, 1, 5), billing_from=date(2026, 1, 5), anchor_day=5)
    generate_missing_charges(sub, renewal_day)
    schedule = schedule_for_subscription(sub)
    assert next_due_date(schedule, renewal_day) == renewal_day

    with patch("plans.selectors.today_dhaka", return_value=renewal_day):
        shown = display_next_renewal(sub)
    assert shown == renewal_day.isoformat()

    spend = report_selectors.dashboard_summary(owner, month=date(2026, 11, 1), today=renewal_day)
    spend_dates = {date.fromisoformat(r["date"]) for r in spend["spend"]["rows"] if r["plan_id"] == sub.pk}
    assert renewal_day in spend_dates

    from tests.test_subscriptions import client_for

    with patch("billing.views.today_dhaka", return_value=renewal_day):
        cal = client_for(owner).get(f"/api/calendar/?month={renewal_day:%Y-%m}").json()
    renewals = [
        date.fromisoformat(e["date"])
        for e in cal["events"]
        if e.get("plan_id") == sub.pk and e.get("kind") == "renews"
    ]
    assert renewal_day in renewals

    owner_user = get_user_model().objects.get(pk=owner.pk)
    owner_user.reminder_days = "0"
    owner_user.email_reminders = False
    owner_user.save(update_fields=["reminder_days", "email_reminders"])
    counts = reminder_services.send_reminders(renewal_day)
    assert counts["owner_reminders"] >= 1
    assert Charge.objects.filter(subscription=sub, due_date=renewal_day).exists()