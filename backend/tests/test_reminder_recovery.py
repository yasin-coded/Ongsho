"""Stage 3B.1/3B.2: reminder outbox recovery and enqueue transaction safety."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.db.transaction import TransactionManagementError

from core.mail_enqueue import OutboxEnqueueError
from core.mail_outbox import enqueue_reminder_delivery
from core.models.outbound_email import OutboundEmail, OutboundEmailStatus, OutboundEmailType
from notifications.models import Notification, Reminder, ReminderChannel
from notifications.reminders import send_reminders

User = get_user_model()


def _double_enqueue_integrity(**kwargs):
    """Provoke a real DB uniqueness failure (duplicate business_event_id) inside one enqueue call."""
    enqueue_reminder_delivery(**kwargs)
    enqueue_reminder_delivery(**kwargs)


def _enable_email_reminders(owner, *, today):
    owner.email_reminders = True
    owner.email_verified = True
    owner.reminder_days = "0"
    owner.save()


@pytest.mark.django_db
def test_first_run_enqueue_error_keeps_reminder_and_notification(world):
    today = world["charge_x"].due_date
    _enable_email_reminders(world["owner"], today=today)
    with patch("core.mail_outbox.enqueue_reminder_delivery", side_effect=OutboxEnqueueError("test")):
        counts = send_reminders(today)
    assert counts["owner_reminders"] >= 1
    assert counts["emails_failed"] >= 1
    assert counts["emails_sent"] == 0
    reminder = Reminder.objects.get(user=world["owner"])
    assert reminder.channel == ReminderChannel.IN_APP
    assert Notification.objects.filter(user=world["owner"]).exists()
    assert not OutboundEmail.objects.filter(
        email_type=OutboundEmailType.REMINDER,
        reminder_id=reminder.pk,
    ).exists()


@pytest.mark.django_db
def test_second_run_recovers_missing_outbox(world):
    today = world["charge_x"].due_date
    _enable_email_reminders(world["owner"], today=today)
    with patch("core.mail_outbox.enqueue_reminder_delivery", side_effect=OutboxEnqueueError("test")):
        send_reminders(today)
    reminder = Reminder.objects.get(user=world["owner"])
    counts = send_reminders(today)
    assert counts["owner_reminders"] == 0
    assert counts["emails_sent"] >= 1
    row = OutboundEmail.objects.get(
        email_type=OutboundEmailType.REMINDER,
        reminder_id=reminder.pk,
    )
    assert row.business_event_id == f"reminder:{reminder.pk}"
    reminder.refresh_from_db()
    assert reminder.channel == ReminderChannel.EMAIL


@pytest.mark.django_db
def test_third_run_no_duplicate_outbox(world):
    today = world["charge_x"].due_date
    _enable_email_reminders(world["owner"], today=today)
    with patch("core.mail_outbox.enqueue_reminder_delivery", side_effect=OutboxEnqueueError("test")):
        send_reminders(today)
    send_reminders(today)
    n = OutboundEmail.objects.filter(email_type=OutboundEmailType.REMINDER).count()
    counts = send_reminders(today)
    assert counts["emails_sent"] == 0
    assert OutboundEmail.objects.filter(email_type=OutboundEmailType.REMINDER).count() == n


@pytest.mark.parametrize(
    "terminal_status",
    [OutboundEmailStatus.SENT, OutboundEmailStatus.CANCELLED, OutboundEmailStatus.FAILED],
)
@pytest.mark.django_db
def test_terminal_outbox_row_blocks_re_enqueue(world, terminal_status):
    today = world["charge_x"].due_date
    _enable_email_reminders(world["owner"], today=today)
    send_reminders(today)
    row = OutboundEmail.objects.get(email_type=OutboundEmailType.REMINDER)
    row.status = terminal_status
    row.save(update_fields=["status", "updated_at"])
    n = OutboundEmail.objects.filter(email_type=OutboundEmailType.REMINDER).count()
    counts = send_reminders(today)
    assert counts["emails_sent"] == 0
    assert OutboundEmail.objects.filter(email_type=OutboundEmailType.REMINDER).count() == n


@pytest.mark.parametrize(
    "active_status",
    [
        OutboundEmailStatus.PENDING,
        OutboundEmailStatus.PROCESSING,
        OutboundEmailStatus.RETRY,
    ],
)
@pytest.mark.django_db
def test_active_outbox_row_blocks_duplicate_enqueue(world, active_status):
    today = world["charge_x"].due_date
    _enable_email_reminders(world["owner"], today=today)
    send_reminders(today)
    row = OutboundEmail.objects.get(email_type=OutboundEmailType.REMINDER)
    row.status = active_status
    row.save(update_fields=["status", "updated_at"])
    n = OutboundEmail.objects.filter(email_type=OutboundEmailType.REMINDER).count()
    counts = send_reminders(today)
    assert counts["emails_sent"] == 0
    assert OutboundEmail.objects.filter(email_type=OutboundEmailType.REMINDER).count() == n


@pytest.mark.django_db
def test_real_db_integrity_error_on_duplicate_business_event_id(world):
    """Violates OutboundEmail.business_event_id unique constraint (second insert in inner savepoint)."""
    today = world["charge_x"].due_date
    _enable_email_reminders(world["owner"], today=today)
    with patch("core.mail_outbox.enqueue_reminder_delivery", side_effect=OutboxEnqueueError("test")):
        send_reminders(today)
    reminder = Reminder.objects.get(user=world["owner"])
    with patch("core.mail_outbox.enqueue_reminder_delivery", side_effect=_double_enqueue_integrity):
        counts = send_reminders(today)
    assert counts["emails_failed"] >= 1
    assert counts["emails_sent"] == 0
    assert not OutboundEmail.objects.filter(
        reminder_id=reminder.pk,
        email_type=OutboundEmailType.REMINDER,
    ).exists()
    reminder.refresh_from_db()
    reminder.channel = ReminderChannel.IN_APP
    reminder.save(update_fields=["channel", "sent_at"])


@pytest.mark.django_db
def test_outer_transaction_usable_after_integrity_error(world):
    today = world["charge_x"].due_date
    _enable_email_reminders(world["owner"], today=today)
    with patch("core.mail_outbox.enqueue_reminder_delivery", side_effect=_double_enqueue_integrity):
        send_reminders(today)
    reminder = Reminder.objects.get(user=world["owner"])
    assert Notification.objects.filter(user=world["owner"]).exists()
    n_before = Notification.objects.filter(user=world["owner"]).count()
    assert Reminder.objects.filter(pk=reminder.pk).exists()
    reminder.refresh_from_db()
    reminder.save(update_fields=["sent_at"])
    assert Notification.objects.filter(user=world["owner"]).count() == n_before


@pytest.mark.django_db
def test_unexpected_integrity_error_not_treated_as_success(world):
    today = world["charge_x"].due_date
    _enable_email_reminders(world["owner"], today=today)
    with patch("core.mail_outbox.enqueue_reminder_delivery", side_effect=_double_enqueue_integrity):
        counts = send_reminders(today)
    assert counts["emails_failed"] >= 1
    assert counts["emails_sent"] == 0


@pytest.mark.django_db
def test_new_reminder_and_notification_survive_enqueue_integrity_failure(world):
    today = world["charge_x"].due_date
    _enable_email_reminders(world["owner"], today=today)
    with patch("core.mail_outbox.enqueue_reminder_delivery", side_effect=_double_enqueue_integrity):
        counts = send_reminders(today)
    assert counts["owner_reminders"] >= 1
    assert counts["emails_failed"] >= 1
    assert Reminder.objects.filter(user=world["owner"]).exists()
    assert Notification.objects.filter(user=world["owner"]).exists()
    assert not OutboundEmail.objects.filter(email_type=OutboundEmailType.REMINDER).exists()


@pytest.mark.django_db(transaction=True)
def test_committed_duplicate_treated_as_already_enqueued(world):
    today = world["charge_x"].due_date
    _enable_email_reminders(world["owner"], today=today)
    with patch("core.mail_outbox.enqueue_reminder_delivery", side_effect=OutboxEnqueueError("test")):
        send_reminders(today)
    reminder = Reminder.objects.get(user=world["owner"])
    send_reminders(today)
    event_id = f"reminder:{reminder.pk}"
    assert OutboundEmail.objects.filter(
        reminder_id=reminder.pk,
        email_type=OutboundEmailType.REMINDER,
        business_event_id=event_id,
    ).exists()

    real_filter = OutboundEmail.objects.filter
    bypass_has_outbox_once = {"pending": True}

    def filter_wrapper(*args, **kwargs):
        qs = real_filter(*args, **kwargs)
        if (
            bypass_has_outbox_once["pending"]
            and kwargs.get("reminder_id") == reminder.pk
            and kwargs.get("email_type") == OutboundEmailType.REMINDER
            and "business_event_id" not in kwargs
        ):
            bypass_has_outbox_once["pending"] = False

            class ExistsOnceFalse:
                def __init__(self, inner):
                    self._inner = inner

                def exists(self):
                    return False

                def __getattr__(self, name):
                    return getattr(self._inner, name)

            return ExistsOnceFalse(qs)
        return qs

    with patch.object(OutboundEmail.objects, "filter", side_effect=filter_wrapper):
        counts = send_reminders(today)
    assert counts["emails_sent"] >= 1
    assert OutboundEmail.objects.filter(reminder_id=reminder.pk).count() == 1
    try:
        Reminder.objects.filter(pk=reminder.pk).exists()
        Notification.objects.filter(user=world["owner"]).count()
    except TransactionManagementError:
        pytest.fail("outer transaction broken after duplicate enqueue handling")


@pytest.mark.django_db
def test_scheduler_continues_after_one_reminder_enqueue_integrity_failure(world):
    send_day = world["today"]
    due = world["due_x"]
    gap = (due.charge.due_date - send_day).days
    owner_gap = (world["charge_x"].due_date - send_day).days
    _enable_email_reminders(world["owner"], today=send_day)
    world["owner"].reminder_days = str(owner_gap)
    world["owner"].save(update_fields=["reminder_days"])
    world["member"].email_reminders = True
    world["member"].email_verified = True
    world["member"].reminder_days = str(gap)
    world["member"].save()

    with patch("core.mail_outbox.enqueue_reminder_delivery", side_effect=OutboxEnqueueError("test")):
        send_reminders(send_day)

    owner_id = world["owner"].pk

    def owner_fails_member_enqueues(**kwargs):
        if kwargs["user"].pk == owner_id:
            _double_enqueue_integrity(**kwargs)
        else:
            enqueue_reminder_delivery(**kwargs)

    with patch("core.mail_outbox.enqueue_reminder_delivery", side_effect=owner_fails_member_enqueues):
        counts = send_reminders(send_day)
    assert counts["emails_failed"] >= 1
    assert not OutboundEmail.objects.filter(user=world["owner"], email_type=OutboundEmailType.REMINDER).exists()
    assert OutboundEmail.objects.filter(user=world["member"], email_type=OutboundEmailType.REMINDER).exists()


@pytest.mark.django_db
def test_disabled_user_not_recovered_to_email(world):
    today = world["charge_x"].due_date
    _enable_email_reminders(world["owner"], today=today)
    with patch("core.mail_outbox.enqueue_reminder_delivery", side_effect=OutboxEnqueueError("test")):
        send_reminders(today)
    world["owner"].email_reminders = False
    world["owner"].save(update_fields=["email_reminders"])
    counts = send_reminders(today)
    assert counts["emails_sent"] == 0
    assert not OutboundEmail.objects.filter(email_type=OutboundEmailType.REMINDER).exists()


@pytest.mark.django_db
def test_unverified_user_not_recovered_to_email(world):
    today = world["charge_x"].due_date
    _enable_email_reminders(world["owner"], today=today)
    with patch("core.mail_outbox.enqueue_reminder_delivery", side_effect=OutboxEnqueueError("test")):
        send_reminders(today)
    world["owner"].email_verified = False
    world["owner"].save(update_fields=["email_verified"])
    counts = send_reminders(today)
    assert counts["emails_sent"] == 0
    assert not OutboundEmail.objects.filter(email_type=OutboundEmailType.REMINDER).exists()


@pytest.mark.django_db
def test_recovery_does_not_duplicate_in_app_notifications(world):
    today = world["charge_x"].due_date
    _enable_email_reminders(world["owner"], today=today)
    with patch("core.mail_outbox.enqueue_reminder_delivery", side_effect=OutboxEnqueueError("test")):
        send_reminders(today)
    n_notifs = Notification.objects.filter(user=world["owner"]).count()
    send_reminders(today)
    assert Notification.objects.filter(user=world["owner"]).count() == n_notifs