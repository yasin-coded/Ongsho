"""Reminder dispatch coverage (additive)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from billing.models import Charge, ChargeStatus
from core.choices import Currency, PaymentMethod
from dues.models import Due, DueStatus
from notifications.models import Notification, Reminder, ReminderKind
from notifications import reminders as reminder_services
from plans.models import CycleUnit, PlanMode, RenewalType, SubscriptionStatus
from sharing.models import Member, MemberStatus, SharedPlan, SplitType

from tests.test_billing_generator import _plan, month_before
from tests.test_subscriptions import WORLD_PASS, client_for, plan_payload

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(db):
    return User.objects.create_user(
        email="rem@example.com",
        password=WORLD_PASS,
        name="Rem",
        email_verified=True,
        reminder_days="7,3,1",
        email_reminders=True,
    )


def _shared_member_plan(owner, member_user, *, start: date):
    client = client_for(owner)
    r = client.post(
        "/api/subscriptions/",
        {**plan_payload(plan_name="Rem Plan", start_date=str(start)), "seats": 2},
        format="json",
    )
    assert r.status_code == 201, r.content
    shared = SharedPlan.objects.get(subscription_id=r.json()["id"])
    sub = shared.subscription
    member = Member.objects.create(
        shared_plan=shared,
        user=member_user,
        share_type=SplitType.EQUAL,
        status=MemberStatus.ACTIVE,
        joined_on=start,
    )
    return sub, shared, member


def test_reminder_custom_days_only_matching_gap(owner):
    today = date(2026, 4, 1)
    target = today + timedelta(days=3)
    owner.reminder_days = "3"
    owner.save(update_fields=["reminder_days"])
    start = month_before(target)
    _plan(owner, start_date=start, billing_from=start, anchor_day=target.day)
    out = reminder_services.send_reminders(today)
    assert out["owner_reminders"] == 1
    owner.reminder_days = "7"
    owner.save(update_fields=["reminder_days"])
    assert reminder_services.send_reminders(today)["owner_reminders"] == 0


def test_reminder_skips_departed_member(owner, db):
    member_user = User.objects.create_user(
        email="gone@example.com", password=WORLD_PASS, name="Gone", email_verified=True, reminder_days="1"
    )
    today = date(2026, 5, 10)
    sub, shared, member = _shared_member_plan(owner, member_user, start=date(2026, 5, 1))
    due_date = today + timedelta(days=1)
    charge = Charge.objects.create(
        subscription=sub,
        period_start=due_date,
        period_end=due_date + timedelta(days=30),
        due_date=due_date,
        amount=Decimal("50.00"),
        amount_bdt=Decimal("50.00"),
        currency=Currency.BDT,
        status=ChargeStatus.DUE,
        locked=False,
    )
    Due.objects.create(charge=charge, member=member, amount_bdt=Decimal("50.00"), status=DueStatus.DUE)
    member.status = MemberStatus.LEFT
    member.left_on = today - timedelta(days=1)
    member.save(update_fields=["status", "left_on"])
    counts = reminder_services.send_reminders(today)
    assert counts["member_reminders"] == 0


def test_reminder_skips_paused_and_cancelled_owner_plans(owner):
    today = date(2026, 6, 1)
    target = today + timedelta(days=7)
    owner.reminder_days = "7"
    owner.save(update_fields=["reminder_days"])
    start = month_before(target)
    _plan(owner, plan_name="Paused", status=SubscriptionStatus.PAUSED, paused_on=today, start_date=start, billing_from=start, anchor_day=target.day)
    _plan(
        owner,
        plan_name="Cancelled",
        status=SubscriptionStatus.CANCELLED,
        cancelled_on=today,
        start_date=start,
        billing_from=start,
        anchor_day=target.day,
    )
    assert reminder_services.send_reminders(today)["owner_reminders"] == 0
    active = _plan(owner, plan_name="Active", start_date=start, billing_from=start, anchor_day=target.day)
    assert active.status == SubscriptionStatus.ACTIVE
    assert reminder_services.send_reminders(today)["owner_reminders"] == 1


def test_reminder_member_message_names_earlier_months(owner, db):
    member_user = User.objects.create_user(
        email="multi@example.com", password=WORLD_PASS, name="Multi", email_verified=True, reminder_days="1"
    )
    today = date(2026, 7, 10)
    sub, shared, member = _shared_member_plan(owner, member_user, start=date(2026, 5, 1))
    early, _ = Charge.objects.get_or_create(
        subscription=sub,
        period_start=date(2026, 6, 1),
        defaults={
            "period_end": date(2026, 6, 30),
            "due_date": date(2026, 6, 5),
            "amount": Decimal("30.00"),
            "amount_bdt": Decimal("30.00"),
            "currency": Currency.BDT,
            "status": ChargeStatus.DUE,
            "locked": True,
        },
    )
    later, _ = Charge.objects.get_or_create(
        subscription=sub,
        period_start=date(2026, 7, 1),
        defaults={
            "period_end": date(2026, 7, 31),
            "due_date": today + timedelta(days=1),
            "amount": Decimal("40.00"),
            "amount_bdt": Decimal("40.00"),
            "currency": Currency.BDT,
            "status": ChargeStatus.DUE,
            "locked": False,
        },
    )
    Charge.objects.filter(pk=later.pk).update(due_date=today + timedelta(days=1))
    later.refresh_from_db()
    due_early, _ = Due.objects.get_or_create(
        charge=early,
        member=member,
        defaults={"amount_bdt": Decimal("30.00"), "status": DueStatus.DUE},
    )
    due_early.status = DueStatus.DUE
    due_early.amount_bdt = Decimal("30.00")
    due_early.save(update_fields=["status", "amount_bdt"])
    due_later, _ = Due.objects.get_or_create(
        charge=later,
        member=member,
        defaults={"amount_bdt": Decimal("40.00"), "status": DueStatus.DUE},
    )
    due_later.status = DueStatus.DUE
    due_later.amount_bdt = Decimal("40.00")
    due_later.save(update_fields=["status", "amount_bdt"])
    reminder_services.send_reminders(today)
    note = Notification.objects.filter(user=member_user, kind="due_soon").latest("id")
    assert "June" in note.message
    assert "70.00" in note.message


def test_reminder_expiry_fixed_term(owner):
    today = date(2026, 8, 1)
    end = today + timedelta(days=7)
    owner.reminder_days = "7"
    owner.save(update_fields=["reminder_days"])
    _plan(
        owner,
        renewal_type=RenewalType.FIXED_TERM,
        end_date=end,
        start_date=date(2026, 1, 1),
        billing_from=date(2026, 1, 1),
        anchor_day=1,
    )
    counts = reminder_services.send_reminders(today)
    assert counts["owner_reminders"] == 1
    assert Reminder.objects.filter(user=owner, kind=ReminderKind.EXPIRY, target_date=end).exists()


def test_reminder_email_failure_counted_without_aborting(owner):
    today = date(2026, 9, 1)
    target = today + timedelta(days=7)
    owner.reminder_days = "7"
    owner.email_reminders = True
    owner.save(update_fields=["reminder_days", "email_reminders"])
    start = month_before(target)
    _plan(owner, start_date=start, billing_from=start, anchor_day=target.day)
    from core.mail_enqueue import OutboxEnqueueError

    with patch("core.mail_outbox.enqueue_reminder_delivery", side_effect=OutboxEnqueueError("boom")):
        counts = reminder_services.send_reminders(today)
    assert counts["owner_reminders"] == 1
    assert counts["emails_failed"] == 1
    assert counts["emails_sent"] == 0
    assert Notification.objects.filter(user=owner, kind="renewal").exists()


def test_reminder_idempotent_same_day_and_multi_day_offsets(owner):
    today = date(2026, 10, 1)
    target = today + timedelta(days=7)
    owner.reminder_days = "7,1"
    owner.save(update_fields=["reminder_days"])
    start = month_before(target)
    _plan(owner, start_date=start, billing_from=start, anchor_day=target.day)

    first = reminder_services.send_reminders(today)
    assert first["owner_reminders"] == 1
    second = reminder_services.send_reminders(today)
    assert second["owner_reminders"] == 0
    assert Reminder.objects.filter(user=owner, target_date=target).count() == 1

    later = reminder_services.send_reminders(today + timedelta(days=6))
    assert later["owner_reminders"] == 1
    assert Reminder.objects.filter(user=owner, target_date=target).count() == 2


@pytest.mark.django_db
def test_run_daily_reminder_sequence_once_per_slot(owner):
    from django.db import connection

    if connection.vendor != "postgresql":
        pytest.skip("advisory lock requires PostgreSQL")
    today = date(2026, 11, 1)
    target = today + timedelta(days=7)
    owner.reminder_days = "7"
    owner.save(update_fields=["reminder_days"])
    start = month_before(target)
    _plan(owner, start_date=start, billing_from=start, anchor_day=target.day)
    out1 = StringIO()
    out2 = StringIO()
    call_command("run_daily", f"--date={today.isoformat()}", stdout=out1)
    call_command("run_daily", f"--date={today.isoformat()}", stdout=out2)
    assert Reminder.objects.filter(user=owner, target_date=target, days_before=7).count() == 1
