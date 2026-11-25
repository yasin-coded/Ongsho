"""Payment rejection emails via transactional outbox (owner reject path only)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.conf import settings
from django.core import mail
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from audit.models import AuditLog
from core.mail_enqueue import OutboxEnqueueError
from core.mail_outbox import enqueue_payment_rejection
from core.models.outbound_email import OutboundEmail, OutboundEmailStatus, OutboundEmailType
from core.outbox.claim import claim_batch
from core.outbox.dispatch import dispatch_outbound_email
from core.outbox.errors import OutboxDeliveryError
from core.outbox.worker import process_claimed_row
from dues.models import Due, DueStatus
from notifications.models import Notification
from payments.models import Payment, ReviewStatus
from tests.outbox_helpers import flush_outbound_to_mailbox
from tests.test_payments import _submit
from tests.test_subscriptions import client_for


def _reject_flow(world, *, tid="REJ0001", reason="Wrong transaction ID"):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    owner = client_for(world["owner"])
    member = client_for(world["member"])
    pay_id = _submit(member, world["plan_x"].pk, [due.pk], transaction_id=tid).json()["payment_id"]
    return owner, pay_id, due, reason


def _reject(owner, pay_id, reason):
    return owner.post(f"/api/payments/{pay_id}/reject/", {"reason": reason}, format="json")


def _claim_token_for(row_id, *, worker_id: str = "pytest-rej") -> str:
    for rid, token in claim_batch(batch_size=50, worker_id=worker_id):
        if rid == row_id:
            return token
    raise AssertionError(f"row {row_id} not claimed")


@pytest.mark.django_db
def test_reject_creates_one_rejection_row(world):
    owner, pay_id, _, reason = _reject_flow(world, tid="REJROW1")
    assert _reject(owner, pay_id, reason).status_code == 200
    audit = AuditLog.objects.get(action="payment.rejected", entity_id=pay_id)
    row = OutboundEmail.objects.get(email_type=OutboundEmailType.PAYMENT_REJECTED)
    assert row.business_event_id == f"payment_rejected:{audit.pk}"
    assert row.user_id == world["member"].pk
    assert row.to_email == world["member"].email
    assert row.payload["payment_id"] == pay_id
    assert row.payload["audit_log_id"] == audit.pk
    assert row.payload["rejection_reason"] == reason
    assert row.payload["link_path"] == f"/app/shared/{world['plan_x'].pk}"
    payment = Payment.objects.get(pk=pay_id)
    assert payment.review_status == ReviewStatus.REJECTED


@pytest.mark.django_db
def test_reject_payload_details(world):
    owner, pay_id, _, reason = _reject_flow(world, tid="REJPAY1")
    _reject(owner, pay_id, reason)
    row = OutboundEmail.objects.get(email_type=OutboundEmailType.PAYMENT_REJECTED)
    assert row.payload["transaction_id"] == "REJPAY1"
    assert "৳" in row.payload["amount_display"]
    assert row.payload["reviewer_name"]


@pytest.mark.django_db
def test_reject_preserves_in_app_notification(world):
    owner, pay_id, _, reason = _reject_flow(world, tid="REJNOT1")
    _reject(owner, pay_id, reason)
    note = Notification.objects.get(user=world["member"], kind="payment_rejected")
    assert note.title == "Payment not confirmed"
    assert note.message == reason


@pytest.mark.django_db
def test_reject_no_sync_send(world):
    owner, pay_id, _, reason = _reject_flow(world, tid="REJSYN1")
    with patch("payments.emails.send_payment_rejected_email") as send_mock:
        _reject(owner, pay_id, reason)
    send_mock.assert_not_called()


@pytest.mark.django_db
def test_reject_without_reason_no_enqueue(world):
    owner, pay_id, _, _ = _reject_flow(world, tid="REJNON1")
    assert owner.post(f"/api/payments/{pay_id}/reject/", {}, format="json").status_code == 400
    assert not OutboundEmail.objects.filter(email_type=OutboundEmailType.PAYMENT_REJECTED).exists()
    assert not AuditLog.objects.filter(action="payment.rejected", entity_id=pay_id).exists()


@pytest.mark.django_db
def test_reject_already_decided_no_second_row(world):
    owner, pay_id, _, reason = _reject_flow(world, tid="REJDUP1")
    _reject(owner, pay_id, reason)
    before = OutboundEmail.objects.filter(email_type=OutboundEmailType.PAYMENT_REJECTED).count()
    assert _reject(owner, pay_id, "again").status_code == 409
    assert OutboundEmail.objects.filter(email_type=OutboundEmailType.PAYMENT_REJECTED).count() == before


@pytest.mark.django_db
def test_reject_enqueue_failure_does_not_rollback(world, caplog):
    owner, pay_id, due, reason = _reject_flow(world, tid="REJRBK1")
    with caplog.at_level("WARNING"):
        with patch("payments.services.enqueue_payment_rejection", side_effect=OutboxEnqueueError("boom")):
            assert _reject(owner, pay_id, reason).status_code == 200
    payment = Payment.objects.get(pk=pay_id)
    assert payment.review_status == ReviewStatus.REJECTED
    due.refresh_from_db()
    assert due.status == DueStatus.DUE
    assert Notification.objects.filter(user=world["member"], kind="payment_rejected").exists()
    assert not OutboundEmail.objects.filter(email_type=OutboundEmailType.PAYMENT_REJECTED).exists()
    assert "payments_rejection_email_enqueue_failed event=payment_rejected" in caplog.text
    assert "boom" not in caplog.text


@pytest.mark.django_db
def test_duplicate_audit_event_id_idempotent(world):
    owner, pay_id, _, reason = _reject_flow(world, tid="REJIDM1")
    _reject(owner, pay_id, reason)
    payment = Payment.objects.get(pk=pay_id)
    audit = AuditLog.objects.get(action="payment.rejected", entity_id=pay_id)
    OutboundEmail.objects.filter(email_type=OutboundEmailType.PAYMENT_REJECTED).delete()
    with transaction.atomic():
        enqueue_payment_rejection(
            payment=payment,
            rejected_by=world["owner"],
            audit_log_id=audit.pk,
            rejection_reason=str((audit.new_value or {}).get("reason") or "x"),
        )
    with transaction.atomic():
        with pytest.raises(IntegrityError):
            enqueue_payment_rejection(
                payment=payment,
                rejected_by=world["owner"],
                audit_log_id=audit.pk,
                rejection_reason=str((audit.new_value or {}).get("reason") or "x"),
            )


@pytest.mark.django_db
def test_confirm_still_unchanged_no_rejection_row(world):
    from tests.test_payment_receipt_outbox import _confirm_flow

    owner, pay_id, _ = _confirm_flow(world, tid="REJCNF1")
    owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    assert OutboundEmail.objects.filter(email_type=OutboundEmailType.PAYMENT_RECEIPT).count() == 1
    assert not OutboundEmail.objects.filter(email_type=OutboundEmailType.PAYMENT_REJECTED).exists()


@pytest.mark.django_db
def test_dispatch_success_body(world, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    owner, pay_id, _, reason = _reject_flow(world, tid="REJDSP1")
    _reject(owner, pay_id, reason)
    mail.outbox.clear()
    flush_outbound_to_mailbox()
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert "Payment not confirmed" in msg.subject
    assert reason in msg.body
    assert "did not confirm your payment submission" in msg.body
    assert settings.FRONTEND_BASE_URL in msg.body


@pytest.mark.django_db
def test_dispatch_inactive_user_cancelled(world, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    owner, pay_id, _, reason = _reject_flow(world, tid="REJINA1")
    _reject(owner, pay_id, reason)
    row = OutboundEmail.objects.get(email_type=OutboundEmailType.PAYMENT_REJECTED)
    world["member"].is_active = False
    world["member"].save(update_fields=["is_active"])
    claim_token = _claim_token_for(row.pk)
    with patch("payments.emails.send_payment_rejected_email") as send_mock:
        outcome = process_claimed_row(row_id=row.pk, claim_token=claim_token)
    assert outcome == "cancelled"
    row.refresh_from_db()
    assert row.last_error_code == "user_inactive"
    send_mock.assert_not_called()


@pytest.mark.django_db
def test_dispatch_recipient_mismatch_failed(world, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    owner, pay_id, _, reason = _reject_flow(world, tid="REJMIS1")
    _reject(owner, pay_id, reason)
    row = OutboundEmail.objects.get(email_type=OutboundEmailType.PAYMENT_REJECTED)
    row.to_email = "other@example.com"
    row.save(update_fields=["to_email", "updated_at"])
    claim_token = _claim_token_for(row.pk)
    with patch("payments.emails.send_payment_rejected_email") as send_mock:
        outcome = process_claimed_row(row_id=row.pk, claim_token=claim_token)
    assert outcome == "failed"
    row.refresh_from_db()
    assert row.last_error_code == "recipient_mismatch"
    send_mock.assert_not_called()


@pytest.mark.django_db
def test_dispatch_payment_not_rejected_cancelled(world, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    owner, pay_id, _, reason = _reject_flow(world, tid="REJST1")
    _reject(owner, pay_id, reason)
    row = OutboundEmail.objects.get(email_type=OutboundEmailType.PAYMENT_REJECTED)
    Payment.objects.filter(pk=pay_id).update(review_status=ReviewStatus.CONFIRMED)
    claim_token = _claim_token_for(row.pk)
    with patch("payments.emails.send_payment_rejected_email") as send_mock:
        outcome = process_claimed_row(row_id=row.pk, claim_token=claim_token)
    assert outcome == "cancelled"
    row.refresh_from_db()
    assert row.last_error_code == "payment_not_rejected"
    send_mock.assert_not_called()


@pytest.mark.django_db
def test_dispatch_audit_not_found_cancelled(world, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    owner, pay_id, _, reason = _reject_flow(world, tid="REJAUD1")
    _reject(owner, pay_id, reason)
    row = OutboundEmail.objects.get(email_type=OutboundEmailType.PAYMENT_REJECTED)
    row.payload = {**(row.payload or {}), "audit_log_id": 999999999}
    row.save(update_fields=["payload", "updated_at"])
    claim_token = _claim_token_for(row.pk)
    with patch("payments.emails.send_payment_rejected_email") as send_mock:
        outcome = process_claimed_row(row_id=row.pk, claim_token=claim_token)
    assert outcome == "cancelled"
    row.refresh_from_db()
    assert row.last_error_code == "audit_not_found"
    send_mock.assert_not_called()


@pytest.mark.django_db
def test_dispatch_audit_reason_mismatch_cancelled(world, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    owner, pay_id, _, reason = _reject_flow(world, tid="REJRSN1")
    _reject(owner, pay_id, reason)
    row = OutboundEmail.objects.get(email_type=OutboundEmailType.PAYMENT_REJECTED)
    row.payload = {**(row.payload or {}), "rejection_reason": "Different reason"}
    row.save(update_fields=["payload", "updated_at"])
    claim_token = _claim_token_for(row.pk)
    with patch("payments.emails.send_payment_rejected_email") as send_mock:
        outcome = process_claimed_row(row_id=row.pk, claim_token=claim_token)
    assert outcome == "cancelled"
    row.refresh_from_db()
    assert row.last_error_code == "invalid_payload"
    send_mock.assert_not_called()


@pytest.mark.django_db
def test_dispatch_user_payment_mismatch(world, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    owner, pay_id, _, reason = _reject_flow(world, tid="REJUSR1")
    _reject(owner, pay_id, reason)
    row = OutboundEmail.objects.get(email_type=OutboundEmailType.PAYMENT_REJECTED)
    row.payload = {**(row.payload or {}), "user_id": world["owner"].pk}
    row.save(update_fields=["payload", "updated_at"])
    claim_token = _claim_token_for(row.pk)
    with patch("payments.emails.send_payment_rejected_email") as send_mock:
        outcome = process_claimed_row(row_id=row.pk, claim_token=claim_token)
    assert outcome == "cancelled"
    row.refresh_from_db()
    assert row.last_error_code == "invalid_payload"
    send_mock.assert_not_called()


@pytest.mark.django_db
def test_dispatch_unit_missing_user():
    row = OutboundEmail(
        email_type=OutboundEmailType.PAYMENT_REJECTED,
        business_event_id="payment_rejected:1",
        to_email="x@example.com",
        payload={"payment_id": 1, "audit_log_id": 1, "user_id": 1},
        user=None,
    )
    with pytest.raises(OutboxDeliveryError) as exc:
        dispatch_outbound_email(row)
    assert exc.value.code == "missing_user"