"""Email change completion notifications via transactional outbox."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from audit.models import AuditLog
from core.mail_enqueue import OutboxEnqueueError
from core.models.outbound_email import OutboundEmail, OutboundEmailStatus, OutboundEmailType
from core.outbox.claim import claim_batch
from core.outbox.worker import process_claimed_row
from tests.outbox_helpers import flush_outbound_to_mailbox
from accounts.tokens import make_email_change_token
from accounts import services as account_services
from core.mail_outbox import enqueue_email_change
from tests.test_profile import (
    client_for,
    make_verified,
    request_email_change,
)

User = get_user_model()


def _verify_email_change(client, token: str):
    return client.post("/api/me/email/verify/", {"token": token}, format="json")


def _pending_user(old="ecc1-old@example.com", new="ecc1-new@example.com"):
    user = make_verified(old)
    client = client_for(user)
    request_email_change(client, new)
    user.refresh_from_db()
    token = make_email_change_token(user, new)
    return user, client, token, old, new


def _claim_token_for(row_id, *, worker_id: str = "pytest-ecc") -> str:
    for rid, token in claim_batch(batch_size=50, worker_id=worker_id):
        if rid == row_id:
            return token
    raise AssertionError(f"row {row_id} not claimed")


@pytest.mark.django_db
def test_verify_queues_exactly_two_completion_rows():
    user, client, token, old, new = _pending_user()
    mail.outbox.clear()
    r = _verify_email_change(client, token)
    assert r.status_code == 200
    user.refresh_from_db()
    assert user.email == new
    audit = AuditLog.objects.get(user=user, action="email_change.verified")
    new_row = OutboundEmail.objects.get(email_type=OutboundEmailType.EMAIL_CHANGED_NEW)
    prev_row = OutboundEmail.objects.get(email_type=OutboundEmailType.EMAIL_CHANGED_PREVIOUS)
    assert new_row.business_event_id == f"email_changed_new:{audit.pk}"
    assert prev_row.business_event_id == f"email_changed_previous:{audit.pk}"
    assert new_row.user_id == user.pk == prev_row.user_id
    assert new_row.to_email == new
    assert prev_row.to_email == old
    assert new_row.payload["audit_log_id"] == audit.pk
    assert prev_row.payload["previous_email"] == old.lower()
    assert OutboundEmail.objects.filter(
        email_type__in=(
            OutboundEmailType.EMAIL_CHANGED_NEW,
            OutboundEmailType.EMAIL_CHANGED_PREVIOUS,
        )
    ).count() == 2


@pytest.mark.django_db
def test_no_sync_send_on_verify():
    user, client, token, _, _ = _pending_user(old="ecc2-old@example.com", new="ecc2-new@example.com")
    with patch("accounts.emails.send_email_changed_new_notice_email") as new_mock, patch(
        "accounts.emails.send_email_changed_previous_notice_email"
    ) as prev_mock:
        _verify_email_change(client, token)
    new_mock.assert_not_called()
    prev_mock.assert_not_called()


@pytest.mark.django_db
def test_dispatch_new_address_success(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    user, client, token, _, new = _pending_user(
        old="ecc3-old@example.com", new="ecc3-new@example.com"
    )
    _verify_email_change(client, token)
    mail.outbox.clear()
    flush_outbound_to_mailbox()
    subjects = {m.subject.lower() for m in mail.outbox}
    assert any("sign-in email was updated" in s for s in subjects)
    recipients = {addr for m in mail.outbox for addr in m.to}
    assert new in recipients


@pytest.mark.django_db
def test_dispatch_previous_address_despite_user_email_mismatch(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    user, client, token, old, new = _pending_user(
        old="ecc4-old@example.com", new="ecc4-new@example.com"
    )
    _verify_email_change(client, token)
    user.refresh_from_db()
    assert user.email == new
    row = OutboundEmail.objects.get(email_type=OutboundEmailType.EMAIL_CHANGED_PREVIOUS)
    assert row.to_email == old
    claim_token = _claim_token_for(row.pk)
    mail.outbox.clear()
    with patch("accounts.emails.send_email_changed_previous_notice_email") as send_mock:
        outcome = process_claimed_row(row_id=row.pk, claim_token=claim_token)
    assert outcome == "sent"
    send_mock.assert_called_once()
    assert send_mock.call_args.kwargs["to_email"] == old


@pytest.mark.django_db
def test_dispatch_previous_recipient_mismatch_cancelled(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    user, client, token, _, _ = _pending_user(
        old="ecc5-old@example.com", new="ecc5-new@example.com"
    )
    _verify_email_change(client, token)
    row = OutboundEmail.objects.get(email_type=OutboundEmailType.EMAIL_CHANGED_PREVIOUS)
    row.to_email = "wrong@example.com"
    row.save(update_fields=["to_email", "updated_at"])
    claim_token = _claim_token_for(row.pk)
    with patch("accounts.emails.send_email_changed_previous_notice_email") as send_mock:
        outcome = process_claimed_row(row_id=row.pk, claim_token=claim_token)
    assert outcome == "cancelled"
    row.refresh_from_db()
    assert row.last_error_code == "previous_recipient_mismatch"
    send_mock.assert_not_called()


@pytest.mark.django_db
def test_dispatch_wrong_audit_cancelled(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    user, client, token, _, _ = _pending_user(
        old="ecc6-old@example.com", new="ecc6-new@example.com"
    )
    _verify_email_change(client, token)
    row = OutboundEmail.objects.get(email_type=OutboundEmailType.EMAIL_CHANGED_NEW)
    row.payload = {**(row.payload or {}), "audit_log_id": 999999999}
    row.save(update_fields=["payload", "updated_at"])
    claim_token = _claim_token_for(row.pk)
    with patch("accounts.emails.send_email_changed_new_notice_email") as send_mock:
        outcome = process_claimed_row(row_id=row.pk, claim_token=claim_token)
    assert outcome == "cancelled"
    row.refresh_from_db()
    assert row.last_error_code == "audit_not_found"
    send_mock.assert_not_called()


@pytest.mark.django_db
def test_dispatch_inactive_user_cancelled(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    user, client, token, _, _ = _pending_user(
        old="ecc7-old@example.com", new="ecc7-new@example.com"
    )
    _verify_email_change(client, token)
    row = OutboundEmail.objects.get(email_type=OutboundEmailType.EMAIL_CHANGED_NEW)
    claim_token = _claim_token_for(row.pk)
    user.is_active = False
    user.save(update_fields=["is_active"])
    with patch("accounts.emails.send_email_changed_new_notice_email") as send_mock:
        outcome = process_claimed_row(row_id=row.pk, claim_token=claim_token)
    assert outcome == "cancelled"
    row.refresh_from_db()
    assert row.last_error_code == "user_inactive"
    send_mock.assert_not_called()


@pytest.mark.django_db
def test_enqueue_failure_does_not_rollback_email_change(caplog):
    user, client, token, old, new = _pending_user(
        old="ecc8-old@example.com", new="ecc8-new@example.com"
    )

    def fail_new(*_a, **_kw):
        raise OutboxEnqueueError("boom")

    with caplog.at_level("WARNING"):
        with patch("accounts.services.enqueue_email_changed_new_notice", side_effect=fail_new):
            r = _verify_email_change(client, token)
    assert r.status_code == 200
    user.refresh_from_db()
    assert user.email == new
    assert user.pending_email == ""
    assert AuditLog.objects.filter(user=user, action="email_change.verified").exists()
    assert not OutboundEmail.objects.filter(email_type=OutboundEmailType.EMAIL_CHANGED_NEW).exists()
    assert "accounts_email_change_notice_enqueue_failed event=email_changed_new" in caplog.text
    assert "boom" not in caplog.text


@pytest.mark.django_db
def test_duplicate_audit_event_id_idempotent():
    user = make_verified("ecc9-new@example.com")
    from core.mail_outbox import enqueue_email_changed_new_notice, enqueue_email_changed_previous_notice

    audit = AuditLog.objects.create(
        user=user,
        action="email_change.verified",
        entity_type="User",
        entity_id=user.pk,
        old_value={"email": "old@example.com"},
        new_value={"email": user.email},
    )
    with transaction.atomic():
        enqueue_email_changed_new_notice(
            user=user,
            audit_log_id=audit.pk,
            previous_email="old@example.com",
            new_email=user.email,
        )
    with transaction.atomic():
        with pytest.raises(IntegrityError):
            enqueue_email_changed_new_notice(
                user=user,
                audit_log_id=audit.pk,
                previous_email="old@example.com",
                new_email=user.email,
            )
    with transaction.atomic():
        enqueue_email_changed_previous_notice(
            user=user,
            audit_log_id=audit.pk,
            previous_email="old@example.com",
            new_email=user.email,
        )
    assert (
        OutboundEmail.objects.filter(business_event_id=f"email_changed_new:{audit.pk}").count() == 1
    )
    assert (
        OutboundEmail.objects.filter(business_event_id=f"email_changed_previous:{audit.pk}").count()
        == 1
    )


@pytest.mark.django_db
def test_cancel_email_change_cancels_pending_verification():
    user = make_verified("ecc10-old@example.com")
    with transaction.atomic():
        user.pending_email = "ecc10-new@example.com"
        user.save(update_fields=["pending_email"])
        enqueue_email_change(user)
    row = OutboundEmail.objects.get(user=user, email_type=OutboundEmailType.EMAIL_CHANGE)
    assert row.status == OutboundEmailStatus.PENDING
    account_services.cancel_email_change(user)
    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.CANCELLED
    assert row.last_error_code == "superseded"


@pytest.mark.django_db
def test_cancel_email_change_leaves_sent_verification(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    user = make_verified("ecc11-old@example.com")
    with transaction.atomic():
        user.pending_email = "ecc11-new@example.com"
        user.save(update_fields=["pending_email"])
        enqueue_email_change(user)
    row = OutboundEmail.objects.get(user=user, email_type=OutboundEmailType.EMAIL_CHANGE)
    claim_token = _claim_token_for(row.pk)
    process_claimed_row(row_id=row.pk, claim_token=claim_token)
    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.SENT
    account_services.cancel_email_change(user)
    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.SENT


@pytest.mark.django_db
def test_idempotent_verify_does_not_enqueue_completion_twice():
    user, client, token, _, _ = _pending_user(
        old="ecc12-old@example.com", new="ecc12-new@example.com"
    )
    _verify_email_change(client, token)
    count = OutboundEmail.objects.filter(
        email_type__in=(
            OutboundEmailType.EMAIL_CHANGED_NEW,
            OutboundEmailType.EMAIL_CHANGED_PREVIOUS,
        )
    ).count()
    again = _verify_email_change(client, token)
    assert again.status_code == 200
    assert (
        OutboundEmail.objects.filter(
            email_type__in=(
                OutboundEmailType.EMAIL_CHANGED_NEW,
                OutboundEmailType.EMAIL_CHANGED_PREVIOUS,
            )
        ).count()
        == count
    )