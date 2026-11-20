"""Verification outbox supersession, inactive users, and worker ownership."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from accounts import services as account_services
from core.mail_outbox import (
    cancel_pending_invite_deliveries,
    enqueue_account_verify,
    enqueue_reminder_delivery,
    enqueue_verify_resend,
)
from core.models.outbound_email import OutboundEmail, OutboundEmailStatus, OutboundEmailType
from core.outbox.dispatch import dispatch_outbound_email
from core.outbox.errors import OutboxDeliveryError
from core.outbox.verification import cancel_pending_verification_deliveries
from core.outbox.worker import _finalize, process_claimed_row

User = get_user_model()


def _unverified_user(*, email: str = "verify-outbox@example.com") -> User:
    return User.objects.create_user(
        email=email,
        password="HorseBatteryStaple99",
        name="Verify Outbox",
        email_verified=False,
    )


def _mark_processing(row: OutboundEmail) -> str:
    claim = uuid.uuid4().hex
    row.status = OutboundEmailStatus.PROCESSING
    row.locked_by = claim
    row.locked_at = timezone.now()
    row.save(update_fields=["status", "locked_by", "locked_at", "updated_at"])
    return claim


@pytest.mark.django_db
def test_enqueue_cancels_pending_and_retry_siblings(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    user = _unverified_user()
    with transaction.atomic():
        first = enqueue_account_verify(user)
    with transaction.atomic():
        second = enqueue_verify_resend(user)
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.status == OutboundEmailStatus.CANCELLED
    assert first.last_error_code == "superseded"
    assert second.status == OutboundEmailStatus.PENDING


@pytest.mark.django_db
def test_enqueue_cancels_retry_sibling(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    user = _unverified_user(email="retry-supersede@example.com")
    with transaction.atomic():
        older = enqueue_account_verify(user)
    older.status = OutboundEmailStatus.RETRY
    older.next_attempt_at = timezone.now()
    older.last_error_code = "provider_503"
    older.save(update_fields=["status", "next_attempt_at", "last_error_code", "updated_at"])

    with transaction.atomic():
        newer = enqueue_verify_resend(user)

    older.refresh_from_db()
    newer.refresh_from_db()
    assert older.status == OutboundEmailStatus.CANCELLED
    assert older.last_error_code == "superseded"
    assert newer.status == OutboundEmailStatus.PENDING


@pytest.mark.django_db
def test_enqueue_does_not_cancel_processing_sibling(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    user = _unverified_user(email="processing-sibling@example.com")
    with transaction.atomic():
        processing = enqueue_account_verify(user)
    processing.status = OutboundEmailStatus.PROCESSING
    processing.locked_by = uuid.uuid4().hex
    processing.locked_at = timezone.now()
    processing.save(update_fields=["status", "locked_by", "locked_at", "updated_at"])

    with transaction.atomic():
        newer = enqueue_verify_resend(user)

    processing.refresh_from_db()
    newer.refresh_from_db()
    assert processing.status == OutboundEmailStatus.PROCESSING
    assert newer.status == OutboundEmailStatus.PENDING


@pytest.mark.django_db
def test_dispatch_superseded_cancels_older_without_send(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    user = _unverified_user(email="supersede-dispatch@example.com")
    with transaction.atomic():
        older = enqueue_account_verify(user)
    with transaction.atomic():
        newer = enqueue_verify_resend(user)
    older.refresh_from_db()
    assert older.status == OutboundEmailStatus.CANCELLED

    older.status = OutboundEmailStatus.PENDING
    older.last_error_code = ""
    older.save(update_fields=["status", "last_error_code", "updated_at"])

    mail.outbox.clear()
    with patch("accounts.emails.send_verification_email") as send_mock:
        with pytest.raises(OutboxDeliveryError) as exc_info:
            dispatch_outbound_email(older)
        assert exc_info.value.code == "superseded"
        send_mock.assert_not_called()


@pytest.mark.django_db
def test_dispatch_inactive_user_never_sends(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    user = _unverified_user(email="inactive-user@example.com")
    user.is_active = False
    user.save(update_fields=["is_active"])
    with transaction.atomic():
        row = enqueue_verify_resend(user)

    mail.outbox.clear()
    with patch("accounts.emails.send_verification_email") as send_mock:
        with pytest.raises(OutboxDeliveryError) as exc_info:
            dispatch_outbound_email(row)
        assert exc_info.value.code == "user_inactive"
        send_mock.assert_not_called()


@pytest.mark.django_db
def test_worker_cancels_already_verified_without_send(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    user = _unverified_user(email="worker-verified@example.com")
    with transaction.atomic():
        row = enqueue_account_verify(user)
    claim = _mark_processing(row)
    user.email_verified = True
    user.save(update_fields=["email_verified"])

    with patch("accounts.emails.send_verification_email") as send_mock:
        outcome = process_claimed_row(row_id=row.pk, claim_token=claim)
        assert outcome == "cancelled"

    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.CANCELLED
    assert row.last_error_code == "already_verified"
    send_mock.assert_not_called()


@pytest.mark.django_db
def test_worker_fails_recipient_mismatch_without_send(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    user = _unverified_user(email="mismatch-worker@example.com")
    with transaction.atomic():
        row = enqueue_account_verify(user)
    row.to_email = "other@example.com"
    row.save(update_fields=["to_email", "updated_at"])
    claim = _mark_processing(row)

    with patch("accounts.emails.send_verification_email") as send_mock:
        outcome = process_claimed_row(row_id=row.pk, claim_token=claim)
        assert outcome == "failed"

    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.FAILED
    assert row.last_error_code == "recipient_mismatch"
    send_mock.assert_not_called()


@pytest.mark.django_db
def test_worker_cancels_superseded_without_send(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    user = _unverified_user(email="worker-superseded@example.com")
    with transaction.atomic():
        older = enqueue_account_verify(user)
    with transaction.atomic():
        enqueue_verify_resend(user)
    older.status = OutboundEmailStatus.PENDING
    older.last_error_code = ""
    older.save(update_fields=["status", "last_error_code", "updated_at"])
    claim = _mark_processing(older)

    with patch("accounts.emails.send_verification_email") as send_mock:
        outcome = process_claimed_row(row_id=older.pk, claim_token=claim)
        assert outcome == "cancelled"

    older.refresh_from_db()
    assert older.status == OutboundEmailStatus.CANCELLED
    assert older.last_error_code == "superseded"
    send_mock.assert_not_called()


@pytest.mark.django_db
def test_worker_cancels_user_inactive_without_send(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    user = _unverified_user(email="worker-inactive@example.com")
    with transaction.atomic():
        row = enqueue_verify_resend(user)
    claim = _mark_processing(row)
    user.is_active = False
    user.save(update_fields=["is_active"])

    with patch("accounts.emails.send_verification_email") as send_mock:
        outcome = process_claimed_row(row_id=row.pk, claim_token=claim)
        assert outcome == "cancelled"

    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.CANCELLED
    assert row.last_error_code == "user_inactive"
    send_mock.assert_not_called()


@pytest.mark.django_db
def test_worker_finalize_requires_matching_claim_token(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    user = _unverified_user(email="finalize-claim@example.com")
    with transaction.atomic():
        row = enqueue_account_verify(user)
    claim = uuid.uuid4().hex
    row.status = OutboundEmailStatus.PROCESSING
    row.locked_by = claim
    row.locked_at = timezone.now()
    row.save(update_fields=["status", "locked_by", "locked_at", "updated_at"])

    wrong = uuid.uuid4().hex
    _finalize(row.pk, wrong, outcome="sent", error_code="")
    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.PROCESSING
    assert row.locked_by == claim

    _finalize(row.pk, claim, outcome="cancelled", error_code="superseded")
    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.CANCELLED
    assert row.last_error_code == "superseded"
    assert row.locked_by == ""


@pytest.mark.django_db
def test_process_claimed_row_skips_when_lock_lost(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    user = _unverified_user(email="skipped-ownership@example.com")
    with transaction.atomic():
        row = enqueue_account_verify(user)
    claim = uuid.uuid4().hex
    row.status = OutboundEmailStatus.PROCESSING
    row.locked_by = claim
    row.locked_at = timezone.now()
    row.save(update_fields=["status", "locked_by", "locked_at", "updated_at"])

    row.locked_by = "other-worker"
    row.save(update_fields=["locked_by", "updated_at"])

    mail.outbox.clear()
    with patch("accounts.emails.send_verification_email") as send_mock:
        outcome = process_claimed_row(row_id=row.pk, claim_token=claim)
        assert outcome == "skipped_ownership"
        send_mock.assert_not_called()


@pytest.mark.django_db
def test_sequential_resends_leave_one_active_pending(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    user = _unverified_user(email="double-resend@example.com")
    with transaction.atomic():
        account_services.resend_verification(user.email)
    cache.clear()
    with transaction.atomic():
        account_services.resend_verification(user.email)

    active = OutboundEmail.objects.filter(
        user_id=user.pk,
        email_type__in=(OutboundEmailType.ACCOUNT_VERIFY, OutboundEmailType.VERIFY_RESEND),
        status__in=(
            OutboundEmailStatus.PENDING,
            OutboundEmailStatus.RETRY,
            OutboundEmailStatus.PROCESSING,
        ),
    )
    assert active.count() == 1
    assert active.get().email_type == OutboundEmailType.VERIFY_RESEND


@pytest.mark.django_db
def test_cancel_pending_verification_does_not_touch_invite_rows(settings, world):
    """Regression: verification cancel helper must not affect plan_invite outbox rows."""
    from sharing.models import Invite, InviteStatus
    from sharing.tokens import new_invite_token
    from core.mail_outbox import enqueue_plan_invite_delivery

    owner = world["owner"]
    shared = world["shared_x"]
    raw, token_hash = new_invite_token()
    invite = Invite.objects.create(
        shared_plan=shared,
        invited_by=owner,
        email="invitee-reserve@example.com",
        token_hash=token_hash,
        expires_on=timezone.now() + timezone.timedelta(days=7),
        status=InviteStatus.PENDING,
    )
    with transaction.atomic():
        invite_row = enqueue_plan_invite_delivery(
            invite=invite,
            raw_token=raw,
            business_event_id=f"plan_invite:test:{invite.pk}",
        )

    cancel_pending_verification_deliveries(owner.pk)
    invite_row.refresh_from_db()
    assert invite_row.status == OutboundEmailStatus.PENDING

    cancel_pending_invite_deliveries(invite.pk)
    invite_row.refresh_from_db()
    assert invite_row.status == OutboundEmailStatus.CANCELLED


@pytest.mark.django_db
def test_verification_supersession_does_not_cancel_reminder_dispatch(settings, world):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    from notifications.models import Reminder, ReminderChannel, ReminderKind

    user = world["owner"]
    user.email_verified = True
    user.email_reminders = True
    user.save(update_fields=["email_verified", "email_reminders"])

    reminder = Reminder.objects.create(
        subscription=world["plan_x"],
        user=user,
        kind=ReminderKind.DUE_SOON,
        target_date=world["due_x"].charge.due_date,
        days_before=3,
        channel=ReminderChannel.EMAIL,
    )
    with transaction.atomic():
        row = enqueue_reminder_delivery(
            reminder=reminder,
            user=user,
            title="Due reminder",
            message="Pay soon",
            link_path="/plans/1",
        )

    cancel_pending_verification_deliveries(user.pk)
    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.PENDING

    claim = _mark_processing(row)
    with patch("notifications.emails.send_reminder_email") as send_mock:
        outcome = process_claimed_row(row_id=row.pk, claim_token=claim)
        assert outcome == "sent"
        send_mock.assert_called_once()

    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.SENT