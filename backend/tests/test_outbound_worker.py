from __future__ import annotations

import logging
import re
import threading
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core import mail
from django.core.management import call_command
from django.db import connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from accounts.models import User
from core.email_backends.brevo import BrevoEmailError
from core.mail_enqueue import enqueue_outbound_email
from core.models.outbound_email import OutboundEmail, OutboundEmailStatus, OutboundEmailType
from core.outbox.claim import claim_batch, count_eligible
from core.outbox.retry import classify_http_status, next_backoff_at
from core.outbox.worker import _finalize, _schedule_retry, process_claimed_row, run_worker_pass
from sharing.models import Invite, InviteStatus
from sharing.tokens import new_invite_token

_CLAIM_TOKEN_RE = re.compile(r"^[a-f0-9]{32}$")


def _enqueue_verify(user, event_id: str | None = None):
    return enqueue_outbound_email(
        email_type=OutboundEmailType.ACCOUNT_VERIFY,
        business_event_id=event_id or f"verify:{uuid.uuid4()}",
        to_email=user.email,
        user=user,
    )


def _claim_token_for(row_id, *, worker_id: str = "w") -> str:
    for rid, token in claim_batch(batch_size=50, worker_id=worker_id):
        if rid == row_id:
            assert _CLAIM_TOKEN_RE.match(token)
            return token
    raise AssertionError("row not claimed")


@pytest.fixture
def mail_user(db):
    return User.objects.create_user(email="worker@example.com", password="pass12345", name="Worker")


def test_claim_pending_row(mail_user):
    with transaction.atomic():
        row = _enqueue_verify(mail_user)
    token = _claim_token_for(row.id)
    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.PROCESSING
    assert row.locked_by == token


def test_respects_next_attempt_at(mail_user):
    with transaction.atomic():
        row = _enqueue_verify(mail_user)
    OutboundEmail.objects.filter(pk=row.pk).update(
        status=OutboundEmailStatus.RETRY,
        next_attempt_at=timezone.now() + timedelta(hours=1),
        locked_at=None,
        locked_by="",
    )
    assert claim_batch(batch_size=10, worker_id="w1") == []


def test_claim_retry_when_due(mail_user):
    with transaction.atomic():
        row = _enqueue_verify(mail_user)
    past = timezone.now() - timedelta(minutes=1)
    OutboundEmail.objects.filter(pk=row.pk).update(
        status=OutboundEmailStatus.RETRY,
        next_attempt_at=past,
        locked_at=None,
        locked_by="",
    )
    token = _claim_token_for(row.id)
    assert token


def test_reclaim_expired_processing_lease(mail_user, settings):
    with transaction.atomic():
        row = _enqueue_verify(mail_user)
    stale = timezone.now() - timedelta(seconds=settings.OUTBOX_LEASE_SECONDS + 10)
    old_token = uuid.uuid4().hex
    OutboundEmail.objects.filter(pk=row.pk).update(
        status=OutboundEmailStatus.PROCESSING,
        locked_at=stale,
        locked_by=old_token,
    )
    new_token = _claim_token_for(row.id, worker_id="same-cron-worker-id")
    row.refresh_from_db()
    assert row.locked_by == new_token
    assert row.locked_by != old_token


def test_active_processing_lease_not_claimed(mail_user, settings):
    with transaction.atomic():
        row = _enqueue_verify(mail_user)
    fresh = timezone.now()
    OutboundEmail.objects.filter(pk=row.pk).update(
        status=OutboundEmailStatus.PROCESSING,
        locked_at=fresh,
        locked_by=uuid.uuid4().hex,
    )
    assert claim_batch(batch_size=10, worker_id="w-other") == []


@pytest.mark.django_db(transaction=True)
class ConcurrentClaimTests(TransactionTestCase):
    def test_concurrent_claim_single_row(self):
        user = User.objects.create_user(email="conc@example.com", password="pass12345", name="C")
        with transaction.atomic():
            row = _enqueue_verify(user)
        results: list[list] = []
        barrier = threading.Barrier(2)

        def claimer():
            barrier.wait()
            connection.close()
            results.append(claim_batch(batch_size=5, worker_id="shared-id"))

        threads = [threading.Thread(target=claimer) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        flat = [rid for batch in results for rid, _tok in batch]
        assert flat.count(row.id) == 1


def test_distinct_claim_tokens_per_row(mail_user):
    with transaction.atomic():
        r1 = _enqueue_verify(mail_user)
        r2 = _enqueue_verify(mail_user, event_id=f"v:{uuid.uuid4()}")
    tokens = {t for _rid, t in claim_batch(batch_size=10, worker_id="ops")}
    assert len(tokens) == 2


def test_successful_delivery_marks_sent(mail_user):
    with transaction.atomic():
        row = _enqueue_verify(mail_user)
    token = _claim_token_for(row.id)
    with patch("accounts.emails.send_verification_email") as send_mock:
        outcome = process_claimed_row(row_id=row.id, claim_token=token)
        send_mock.assert_called_once()
    assert outcome == "sent"
    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.SENT


def test_network_failure_schedules_retry(mail_user):
    with transaction.atomic():
        row = _enqueue_verify(mail_user)
    token = _claim_token_for(row.id)
    with patch("accounts.emails.send_verification_email", side_effect=ConnectionError("down")):
        outcome = process_claimed_row(row_id=row.id, claim_token=token)
    assert outcome == "retry"
    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.RETRY
    assert row.attempt_count == 1


def test_http_429_retry_with_backoff(mail_user):
    with transaction.atomic():
        row = _enqueue_verify(mail_user)
    token = _claim_token_for(row.id)
    with patch(
        "accounts.emails.send_verification_email",
        side_effect=BrevoEmailError("Brevo returned HTTP 429."),
    ):
        outcome = process_claimed_row(row_id=row.id, claim_token=token)
    assert outcome == "retry"
    row.refresh_from_db()
    assert row.last_error_code == "rate_limited"


def test_http_5xx_retry(mail_user):
    with transaction.atomic():
        row = _enqueue_verify(mail_user)
    token = _claim_token_for(row.id)
    with patch(
        "accounts.emails.send_verification_email",
        side_effect=BrevoEmailError("Brevo returned HTTP 503."),
    ):
        process_claimed_row(row_id=row.id, claim_token=token)
    row.refresh_from_db()
    assert row.last_error_code == "provider_5xx"


def test_http_4xx_permanent_failed(mail_user):
    with transaction.atomic():
        row = _enqueue_verify(mail_user)
    token = _claim_token_for(row.id)
    with patch(
        "accounts.emails.send_verification_email",
        side_effect=BrevoEmailError("Brevo returned HTTP 400."),
    ):
        outcome = process_claimed_row(row_id=row.id, claim_token=token)
    assert outcome == "failed"
    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.FAILED


def test_max_attempts_exhaustion(mail_user, settings):
    settings.OUTBOUND_EMAIL_MAX_ATTEMPTS = 2
    with transaction.atomic():
        row = _enqueue_verify(mail_user)
    token = _claim_token_for(row.id)
    OutboundEmail.objects.filter(pk=row.pk).update(attempt_count=1)
    with patch("accounts.emails.send_verification_email", side_effect=ConnectionError("x")):
        process_claimed_row(row_id=row.id, claim_token=token)
    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.FAILED
    assert row.last_error_code == "max_attempts"


def test_stale_claim_token_cannot_finalize(mail_user):
    with transaction.atomic():
        row = _enqueue_verify(mail_user)
    token = _claim_token_for(row.id)
    _finalize(row.id, "deadbeef" * 4, outcome="sent", error_code="")
    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.PROCESSING


def test_stale_claim_token_cannot_retry(mail_user):
    with transaction.atomic():
        row = _enqueue_verify(mail_user)
    token = _claim_token_for(row.id)
    _schedule_retry(row.id, "deadbeef" * 4, error_code="network_error", retry_after_seconds=None)
    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.PROCESSING
    assert row.attempt_count == 0


def test_stale_claim_token_cannot_wipe_ciphertext(db, world):
    raw, token_hash = new_invite_token()
    invite = Invite.objects.create(
        shared_plan=world["shared_x"],
        invited_by=world["owner"],
        email="fence@example.com",
        token_hash=token_hash,
        expires_on=timezone.now() + timedelta(days=3),
        status=InviteStatus.PENDING,
    )
    with transaction.atomic():
        row = enqueue_outbound_email(
            email_type=OutboundEmailType.PLAN_INVITE,
            business_event_id=f"invite:{uuid.uuid4()}",
            to_email=invite.email,
            invite=invite,
            invite_delivery_secret=raw,
        )
    old_token = _claim_token_for(row.id)
    OutboundEmail.objects.filter(pk=row.pk).update(
        locked_at=timezone.now() - timedelta(seconds=99999),
    )
    new_token = _claim_token_for(row.id, worker_id="same-cron-worker-id")
    _finalize(row.id, old_token, outcome="sent", error_code="", wipe_secret=True)
    row.refresh_from_db()
    assert row.locked_by == new_token
    assert row.delivery_ciphertext is not None


def test_reclaimed_row_completes_with_new_token(mail_user):
    with transaction.atomic():
        row = _enqueue_verify(mail_user)
    old_token = _claim_token_for(row.id)
    OutboundEmail.objects.filter(pk=row.pk).update(
        locked_at=timezone.now() - timedelta(seconds=99999),
    )
    new_token = _claim_token_for(row.id, worker_id="same-cron-worker-id")
    with patch("accounts.emails.send_verification_email"):
        assert process_claimed_row(row_id=row.id, claim_token=old_token) == "skipped_ownership"
        assert process_claimed_row(row_id=row.id, claim_token=new_token) == "sent"
    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.SENT


def test_old_token_pre_send_check_after_reclaim(mail_user):
    with transaction.atomic():
        row = _enqueue_verify(mail_user)
    old_token = _claim_token_for(row.id)
    OutboundEmail.objects.filter(pk=row.pk).update(
        locked_at=timezone.now() - timedelta(seconds=99999),
    )
    _claim_token_for(row.id, worker_id="same-cron-worker-id")
    with patch("accounts.emails.send_verification_email") as send_mock:
        outcome = process_claimed_row(row_id=row.id, claim_token=old_token)
    assert outcome == "skipped_ownership"
    send_mock.assert_not_called()


def test_reminder_missing_payload_cancelled(db, world):
    user = world["owner"]
    from notifications.models import Reminder, ReminderChannel, ReminderKind

    reminder = Reminder.objects.create(
        subscription=world["plan_x"],
        user=user,
        kind=ReminderKind.DUE_SOON,
        target_date=timezone.now().date(),
        days_before=3,
        channel=ReminderChannel.IN_APP,
        sent_at=timezone.now(),
    )
    with transaction.atomic():
        row = enqueue_outbound_email(
            email_type=OutboundEmailType.REMINDER,
            business_event_id=f"reminder:{uuid.uuid4()}",
            to_email=user.email,
            user=user,
            reminder=reminder,
            payload={},
        )
    token = _claim_token_for(row.id)
    outcome = process_claimed_row(row_id=row.id, claim_token=token)
    assert outcome == "cancelled"


def test_invite_token_stale_cancelled(db, world):
    raw, token_hash = new_invite_token()
    invite = Invite.objects.create(
        shared_plan=world["shared_x"],
        invited_by=world["owner"],
        email="stale@example.com",
        token_hash=token_hash,
        expires_on=timezone.now() + timedelta(days=7),
        status=InviteStatus.PENDING,
    )
    with transaction.atomic():
        row = enqueue_outbound_email(
            email_type=OutboundEmailType.PLAN_INVITE,
            business_event_id=f"invite:{uuid.uuid4()}",
            to_email=invite.email,
            invite=invite,
            invite_delivery_secret=raw,
        )
    _, new_hash = new_invite_token()
    Invite.objects.filter(pk=invite.pk).update(token_hash=new_hash)
    token = _claim_token_for(row.id)
    with patch("sharing.emails.send_invite_email") as send_mock:
        outcome = process_claimed_row(row_id=row.id, claim_token=token)
        send_mock.assert_not_called()
    assert outcome == "cancelled"
    row.refresh_from_db()
    assert row.delivery_ciphertext is None


def test_no_sensitive_data_in_logs(mail_user, caplog):
    caplog.set_level(logging.INFO)
    with transaction.atomic():
        row = _enqueue_verify(mail_user)
    token = _claim_token_for(row.id)
    with patch("accounts.emails.send_verification_email"):
        process_claimed_row(row_id=row.id, claim_token=token)
    combined = " ".join(r.message for r in caplog.records)
    assert "eyJ" not in combined


def test_dry_run_command(mail_user):
    from io import StringIO

    with transaction.atomic():
        _enqueue_verify(mail_user)
    buf = StringIO()
    call_command("process_email_outbox", "--dry-run", "--no-advisory-lock", stdout=buf)
    assert "eligible=1" in buf.getvalue()


def test_retry_after_honored_in_backoff():
    t0 = timezone.now()
    t1 = next_backoff_at(1, retry_after_seconds=120)
    assert (t1 - t0).total_seconds() >= 120


def test_classify_429():
    err = classify_http_status(429, retry_after_seconds=90)
    assert err.retry_after_seconds == 90


def test_run_worker_pass_integrated(mail_user):
    with transaction.atomic():
        _enqueue_verify(mail_user)
    with patch("accounts.emails.send_verification_email"):
        result = run_worker_pass(batch_size=10, worker_id="integrated", max_runtime_seconds=30.0)
    assert result.sent >= 1


def test_email_change_pending_address_accepted(db):
    user = User.objects.create_user(email="old@example.com", password="pass12345", name="U")
    user.pending_email = "new@example.com"
    user.save(update_fields=["pending_email"])
    with transaction.atomic():
        row = enqueue_outbound_email(
            email_type=OutboundEmailType.EMAIL_CHANGE,
            business_event_id=f"email_change:{uuid.uuid4()}",
            to_email="new@example.com",
            user=user,
        )
    token = _claim_token_for(row.id)
    mail.outbox = []
    with patch("accounts.emails.send_email_change_verification") as send_mock:
        outcome = process_claimed_row(row_id=row.id, claim_token=token)
        send_mock.assert_called_once_with(user, "new@example.com")
    assert outcome == "sent"


def test_email_change_sends_to_new_address(db):
    user = User.objects.create_user(email="primary@example.com", password="pass12345", name="U")
    user.pending_email = "pending@example.com"
    user.save(update_fields=["pending_email"])
    with transaction.atomic():
        row = enqueue_outbound_email(
            email_type=OutboundEmailType.EMAIL_CHANGE,
            business_event_id=f"email_change:{uuid.uuid4()}",
            to_email="pending@example.com",
            user=user,
        )
    token = _claim_token_for(row.id)
    mail.outbox = []
    with patch("accounts.emails.send_mail") as send_mock:
        process_claimed_row(row_id=row.id, claim_token=token)
        kwargs = send_mock.call_args.kwargs
        assert kwargs.get("recipient_list") == ["pending@example.com"]
        assert user.email not in kwargs.get("recipient_list", [])


def test_email_change_mismatch_cancelled(db):
    user = User.objects.create_user(email="old@example.com", password="pass12345", name="U")
    user.pending_email = "new@example.com"
    user.save(update_fields=["pending_email"])
    with transaction.atomic():
        row = enqueue_outbound_email(
            email_type=OutboundEmailType.EMAIL_CHANGE,
            business_event_id=f"email_change:{uuid.uuid4()}",
            to_email="other@example.com",
            user=user,
        )
    token = _claim_token_for(row.id)
    with patch("accounts.emails.send_email_change_verification") as send_mock:
        outcome = process_claimed_row(row_id=row.id, claim_token=token)
        send_mock.assert_not_called()
    assert outcome == "cancelled"
    row.refresh_from_db()
    assert row.last_error_code == "pending_email_mismatch"


def test_email_change_missing_pending_cancelled(db):
    user = User.objects.create_user(email="only@example.com", password="pass12345", name="U")
    with transaction.atomic():
        row = enqueue_outbound_email(
            email_type=OutboundEmailType.EMAIL_CHANGE,
            business_event_id=f"email_change:{uuid.uuid4()}",
            to_email="only@example.com",
            user=user,
        )
    token = _claim_token_for(row.id)
    with patch("accounts.emails.send_email_change_verification") as send_mock:
        outcome = process_claimed_row(row_id=row.id, claim_token=token)
        send_mock.assert_not_called()
    assert outcome == "cancelled"
    row.refresh_from_db()
    assert row.last_error_code == "missing_pending_email"


def test_email_change_does_not_use_primary_recipient_check(db):
    user = User.objects.create_user(email="primary@example.com", password="pass12345", name="U")
    user.pending_email = "next@example.com"
    user.save(update_fields=["pending_email"])
    with transaction.atomic():
        row = enqueue_outbound_email(
            email_type=OutboundEmailType.EMAIL_CHANGE,
            business_event_id=f"email_change:{uuid.uuid4()}",
            to_email="next@example.com",
            user=user,
        )
    token = _claim_token_for(row.id)
    with patch("accounts.emails.send_email_change_verification") as send_mock:
        assert process_claimed_row(row_id=row.id, claim_token=token) == "sent"
    send_mock.assert_called_once()