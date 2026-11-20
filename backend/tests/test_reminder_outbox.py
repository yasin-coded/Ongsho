"""Stage 3B: optional reminder emails via transactional outbox."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import IntegrityError

from accounts import services as account_services
from core.models.outbound_email import OutboundEmail, OutboundEmailStatus, OutboundEmailType
from core.outbox.claim import claim_batch
from core.outbox.worker import process_claimed_row
from notifications.models import Notification, Reminder
from notifications.reminders import send_reminders
from tests.outbox_helpers import flush_outbound_to_mailbox

User = get_user_model()


def _flush_mail():
    mail.outbox.clear()
    flush_outbound_to_mailbox()


@pytest.mark.django_db
def test_enabled_user_gets_reminder_outbox_row(world):
    today = world["charge_x"].due_date
    world["owner"].email_reminders = True
    world["owner"].reminder_days = "0"
    world["owner"].save()
    send_reminders(today)
    row = OutboundEmail.objects.get(
        email_type=OutboundEmailType.REMINDER,
        user=world["owner"],
    )
    assert row.reminder_id
    assert row.business_event_id == f"reminder:{row.reminder_id}"
    assert row.payload["link_path"].startswith("/app/")


@pytest.mark.django_db
def test_disabled_user_no_reminder_outbox(world):
    today = world["charge_x"].due_date
    world["owner"].email_reminders = False
    world["owner"].reminder_days = "0"
    world["owner"].save()
    send_reminders(today)
    assert not OutboundEmail.objects.filter(email_type=OutboundEmailType.REMINDER).exists()
    assert Reminder.objects.filter(user=world["owner"]).exists()
    assert Notification.objects.filter(user=world["owner"]).exists()


@pytest.mark.django_db
def test_reminder_days_respected(world):
    today = world["today"]
    gap = (world["charge_x"].due_date - today).days
    world["owner"].email_reminders = True
    world["owner"].reminder_days = str(gap + 1)
    world["owner"].save()
    assert send_reminders(today)["owner_reminders"] == 0
    world["owner"].reminder_days = str(gap)
    world["owner"].save()
    assert send_reminders(today)["owner_reminders"] >= 1


@pytest.mark.django_db
def test_repeated_scheduler_no_duplicate_deliveries(world):
    world["owner"].reminder_days = "0"
    world["owner"].email_reminders = True
    world["owner"].save()
    t = world["charge_x"].due_date
    send_reminders(t)
    n_rows = OutboundEmail.objects.filter(email_type=OutboundEmailType.REMINDER).count()
    send_reminders(t)
    assert OutboundEmail.objects.filter(email_type=OutboundEmailType.REMINDER).count() == n_rows


@pytest.mark.django_db
def test_successful_delivery_marks_sent(world):
    today = world["charge_x"].due_date
    world["owner"].email_reminders = True
    world["owner"].reminder_days = "0"
    world["owner"].save()
    send_reminders(today)
    row = OutboundEmail.objects.get(email_type=OutboundEmailType.REMINDER)
    _flush_mail()
    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.SENT
    assert row.sent_at


@pytest.mark.django_db
def test_retryable_failure_schedules_retry(world, settings):
    today = world["charge_x"].due_date
    world["owner"].email_reminders = True
    world["owner"].reminder_days = "0"
    world["owner"].save()
    send_reminders(today)
    row = OutboundEmail.objects.get(email_type=OutboundEmailType.REMINDER)
    token = claim_batch(batch_size=1, worker_id="rtest")[0][1]
    with patch("notifications.emails.send_reminder_email", side_effect=ConnectionError("timeout")):
        assert process_claimed_row(row_id=row.id, claim_token=token) == "retry"
    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.RETRY
    assert row.next_attempt_at


@pytest.mark.django_db
def test_reminder_delete_cancels_pending_outbox(world):
    today = world["charge_x"].due_date
    world["owner"].email_reminders = True
    world["owner"].reminder_days = "0"
    world["owner"].save()
    send_reminders(today)
    row = OutboundEmail.objects.get(email_type=OutboundEmailType.REMINDER)
    reminder = Reminder.objects.get(pk=row.reminder_id)
    reminder.delete()
    assert not OutboundEmail.objects.filter(pk=row.pk).exists()


@pytest.mark.django_db
def test_dispatch_opt_out_at_send_time_cancels(world):
    today = world["charge_x"].due_date
    world["owner"].email_reminders = True
    world["owner"].reminder_days = "0"
    world["owner"].save()
    send_reminders(today)
    row = OutboundEmail.objects.get(email_type=OutboundEmailType.REMINDER)
    world["owner"].email_reminders = False
    world["owner"].save(update_fields=["email_reminders"])
    token = claim_batch(batch_size=1, worker_id="opt")[0][1]
    assert process_claimed_row(row_id=row.id, claim_token=token) == "cancelled"


@pytest.mark.django_db
def test_opt_out_cancels_pending(world):
    today = world["charge_x"].due_date
    world["owner"].email_reminders = True
    world["owner"].reminder_days = "0"
    world["owner"].save()
    send_reminders(today)
    row = OutboundEmail.objects.get(email_type=OutboundEmailType.REMINDER, status=OutboundEmailStatus.PENDING)
    account_services.update_reminder_settings(world["owner"], email=False)
    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.CANCELLED


@pytest.mark.django_db
def test_in_app_notify_never_enqueues_outbox(world):
    today = world["charge_x"].due_date
    world["owner"].email_reminders = False
    world["owner"].reminder_days = "0"
    world["owner"].save()
    before = OutboundEmail.objects.count()
    send_reminders(today)
    assert OutboundEmail.objects.count() == before
    assert Notification.objects.filter(user=world["owner"]).exists()


@pytest.mark.django_db
def test_reminder_email_content_unchanged(world, settings):
    today = world["charge_x"].due_date
    world["owner"].email_reminders = True
    world["owner"].reminder_days = "0"
    world["owner"].save()
    send_reminders(today)
    notif = Notification.objects.filter(user=world["owner"]).latest("id")
    _flush_mail()
    msg = mail.outbox[-1]
    assert msg.subject == notif.title
    assert notif.message in msg.body
    assert f"{settings.FRONTEND_BASE_URL}/app/plans/" in msg.body


@pytest.mark.django_db
def test_one_active_row_per_reminder_db_constraint(world):
    today = world["charge_x"].due_date
    world["owner"].email_reminders = True
    world["owner"].reminder_days = "0"
    world["owner"].save()
    send_reminders(today)
    row = OutboundEmail.objects.get(email_type=OutboundEmailType.REMINDER)
    with pytest.raises(IntegrityError):
        OutboundEmail.objects.create(
            email_type=OutboundEmailType.REMINDER,
            business_event_id="reminder:duplicate-test",
            to_email=world["owner"].email,
            user=world["owner"],
            reminder_id=row.reminder_id,
            reminder=row.reminder,
            status=OutboundEmailStatus.PENDING,
        )