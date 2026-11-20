"""Reminder dispatch and daily job integration."""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core import mail

from billing.services import generate_missing_charges
from core.dates import today_dhaka
from dues import services as dues_services
from dues.models import Due, DueStatus
from notifications.models import Notification, Reminder
from notifications.reminders import send_reminders
from plans.models import CycleUnit, RenewalType, SubscriptionStatus
from sharing.models import MemberStatus
from tests.test_billing_generator import _plan, month_before
from tests.test_subscriptions import WORLD_PASS

User = get_user_model()


@pytest.mark.django_db
@pytest.mark.parametrize("days", [7, 3, 1, 0])
def test_owner_renewal_on_each_reminder_day(days):
    today = date(2026, 2, 1)
    target = today + timedelta(days=days)
    owner = User.objects.create_user(
        email=f"own-{days}@example.com",
        password=WORLD_PASS,
        name="Own",
        email_verified=True,
        reminder_days=str(days),
        email_reminders=False,
    )
    start = month_before(target)
    _plan(owner, anchor_day=target.day, start_date=start, billing_from=start)
    counts = send_reminders(today)
    assert counts["owner_reminders"] >= 1
    assert Reminder.objects.filter(user=owner, kind="renewal", days_before=days).exists()
    assert Notification.objects.filter(user=owner, kind="renewal").exists()


@pytest.mark.django_db
def test_empty_reminder_days_send_none(world):
    world["owner"].reminder_days = ""
    world["owner"].save(update_fields=["reminder_days"])
    today = today_dhaka()
    before = Reminder.objects.count()
    counts = send_reminders(today)
    assert counts["owner_reminders"] == 0 and counts["member_reminders"] == 0
    assert Reminder.objects.count() == before


@pytest.mark.django_db
def test_email_off_in_app_only(world):
    today = world["charge_x"].due_date
    world["owner"].email_reminders = False
    world["owner"].reminder_days = "0"
    world["owner"].save()
    from core.models.outbound_email import OutboundEmail, OutboundEmailType
    from tests.outbox_helpers import flush_outbound_to_mailbox

    mail.outbox.clear()
    send_reminders(today)
    flush_outbound_to_mailbox()
    assert not mail.outbox
    assert not OutboundEmail.objects.filter(email_type=OutboundEmailType.REMINDER).exists()
    assert Reminder.objects.filter(user=world["owner"], channel="in_app").exists()


@pytest.mark.django_db
def test_email_on_sends_link(world):
    today = world["charge_x"].due_date
    world["owner"].email_reminders = True
    world["owner"].reminder_days = "0"
    world["owner"].save()
    from core.models.outbound_email import OutboundEmail, OutboundEmailType
    from tests.outbox_helpers import flush_outbound_to_mailbox

    mail.outbox.clear()
    send_reminders(today)
    assert OutboundEmail.objects.filter(email_type=OutboundEmailType.REMINDER).exists()
    flush_outbound_to_mailbox()
    assert mail.outbox
    assert "/app/plans/" in mail.outbox[0].body


@pytest.mark.django_db
def test_second_run_idempotent(world):
    world["owner"].reminder_days = "0"
    world["owner"].save()
    t = world["charge_x"].due_date
    c1 = send_reminders(t)
    n1 = Notification.objects.filter(user=world["owner"]).count()
    c2 = send_reminders(t)
    assert c2["owner_reminders"] == 0
    assert Notification.objects.filter(user=world["owner"]).count() == n1
    assert c1["owner_reminders"] >= 1 or c1["member_reminders"] >= 1


@pytest.mark.django_db
def test_member_due_reminder_skips_paid(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save()
    world["member"].reminder_days = "7"
    world["member"].email_reminders = False
    world["member"].save()
    gap = (due.charge.due_date - world["today"]).days
    if gap in (7, 3, 1, 0):
        world["member"].reminder_days = str(gap)
        world["member"].save(update_fields=["reminder_days"])
        counts = send_reminders(world["today"])
        assert counts["member_reminders"] >= 1
    due.status = DueStatus.PAID
    due.save()
    counts2 = send_reminders(world["today"])
    assert counts2["member_reminders"] == 0


@pytest.mark.django_db
def test_trial_end_reminder():
    today = date(2026, 1, 15)
    owner = User.objects.create_user(
        email="trial@example.com", password=WORLD_PASS, name="Trial", email_verified=True, reminder_days="7"
    )
    sub = _plan(
        owner,
        trial_end_date=date(2026, 1, 22),
        status=SubscriptionStatus.TRIAL,
        billing_from=date(2026, 1, 5),
    )
    send_reminders(today)
    assert Notification.objects.filter(user=owner, kind="trial_end").exists()


@pytest.mark.django_db
def test_run_daily_includes_send_reminders():
    calls = []

    def track(name):
        calls.append(name)
        return 0 if name != "reminders" else {
            "owner_reminders": 0,
            "member_reminders": 0,
            "emails_sent": 0,
            "emails_failed": 0,
        }

    with (
        patch("sharing.services.close_departed_members", side_effect=lambda t: track("depart") or 0),
        patch("billing.services.expire_fixed_term_plans", side_effect=lambda t: track("expire") or 0),
        patch("billing.services.activate_ended_trials", side_effect=lambda t: track("trial") or 0),
        patch("billing.services.generate_charges_for_all_plans", side_effect=lambda t: track("gen") or {"plans": 0, "created": 0, "errors": 0}),
        patch("billing.services.lock_due_charges", side_effect=lambda t: track("lock") or 0),
        patch("dues.services.ensure_dues", side_effect=lambda t: track("dues") or 0),
        patch("notifications.reminders.send_reminders", side_effect=lambda t: track("reminders")),
    ):
        from jobs import services as job_services

        job_services.run_daily(date(2026, 1, 1))
    assert calls == ["depart", "expire", "trial", "gen", "lock", "dues", "reminders"]
