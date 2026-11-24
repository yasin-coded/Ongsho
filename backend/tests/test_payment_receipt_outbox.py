"""Payment receipt emails via transactional outbox (confirm path only)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.conf import settings
from django.core import mail
from django.db import IntegrityError, transaction
from django.utils import timezone

from audit.models import AuditLog
from core.choices import PaymentMethod
from core.mail_enqueue import OutboxEnqueueError, OutboxPayloadError, enqueue_outbound_email
from core.models.outbound_email import OutboundEmail, OutboundEmailStatus, OutboundEmailType
from core.outbox.claim import claim_batch
from core.outbox.dispatch import dispatch_outbound_email
from core.outbox.errors import OutboxDeliveryError
from core.outbox.worker import process_claimed_row
from dues.models import Due, DueStatus
from notifications.models import Notification
from payments.models import Payment, ReviewStatus
from tests.helpers import run_concurrently
from tests.outbox_helpers import flush_outbound_to_mailbox
from tests.test_payments import _submit
from tests.test_subscriptions import client_for


def _confirm_flow(world, *, tid="RCPT0001"):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    owner = client_for(world["owner"])
    member = client_for(world["member"])
    pay_id = _submit(member, world["plan_x"].pk, [due.pk], transaction_id=tid).json()["payment_id"]
    return owner, pay_id, due


def _assert_confirm_enqueue_rollback(world, pay_id, due):
    payment = Payment.objects.get(pk=pay_id)
    assert payment.review_status == ReviewStatus.PENDING
    due.refresh_from_db()
    assert due.status == DueStatus.PENDING
    assert not Notification.objects.filter(user=world["member"], kind="payment_confirmed").exists()
    assert not OutboundEmail.objects.filter(email_type=OutboundEmailType.PAYMENT_RECEIPT).exists()
    assert not AuditLog.objects.filter(
        action="payment.confirmed",
        entity_type="Payment",
        entity_id=pay_id,
    ).exists()


@pytest.mark.django_db
def test_confirm_creates_one_receipt_row(world):
    owner, pay_id, due = _confirm_flow(world)
    assert owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json").status_code == 200
    row = OutboundEmail.objects.get(email_type=OutboundEmailType.PAYMENT_RECEIPT)
    assert row.business_event_id == f"payment_receipt:{pay_id}"
    assert row.user_id == world["member"].pk
    assert row.to_email == world["member"].email
    assert row.payload["payment_id"] == pay_id
    assert row.payload["link_path"] == f"/app/shared/{world['plan_x'].pk}"
    due.refresh_from_db()
    assert due.status == DueStatus.PAID


@pytest.mark.django_db
def test_confirm_payload_bdt_and_usd_note(world):
    world["plan_x"].currency = "USD"
    world["plan_x"].save(update_fields=["currency"])
    owner, pay_id, _ = _confirm_flow(world, tid="RCPTUSD1")
    owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    row = OutboundEmail.objects.get(business_event_id=f"payment_receipt:{pay_id}")
    assert row.payload["subscription_currency"] == "USD"
    assert "৳" in row.payload["amount_display"]
    assert "payment_id" in row.payload


@pytest.mark.django_db
def test_confirm_preserves_in_app_notification(world):
    owner, pay_id, _ = _confirm_flow(world, tid="RCPTNOT1")
    owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    assert Notification.objects.filter(user=world["member"], kind="payment_confirmed").exists()
    assert OutboundEmail.objects.filter(email_type=OutboundEmailType.PAYMENT_RECEIPT).count() == 1


@pytest.mark.django_db
def test_confirm_no_sync_send(world):
    owner, pay_id, _ = _confirm_flow(world, tid="RCPTSYN1")
    with patch("payments.emails.send_payment_receipt_email") as send_mock:
        owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
        send_mock.assert_not_called()


@pytest.mark.django_db
def test_confirm_enqueue_failure_rolls_back(world):
    owner, pay_id, due = _confirm_flow(world, tid="RCPTRBK1")
    with patch("payments.services.enqueue_payment_receipt", side_effect=OutboxEnqueueError("boom")):
        r = owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "confirm_failed"
    _assert_confirm_enqueue_rollback(world, pay_id, due)


@pytest.mark.django_db
def test_confirm_payload_error_rolls_back(world):
    owner, pay_id, due = _confirm_flow(world, tid="RCPTPAY1")
    with patch(
        "payments.services.enqueue_payment_receipt",
        side_effect=OutboxPayloadError("unsafe payload"),
    ):
        r = owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "confirm_failed"
    _assert_confirm_enqueue_rollback(world, pay_id, due)


@pytest.mark.django_db
def test_confirm_integrity_error_rolls_back(world):
    owner, pay_id, due = _confirm_flow(world, tid="RCPTINT1")
    with patch(
        "payments.services.enqueue_payment_receipt",
        side_effect=IntegrityError("duplicate business_event_id"),
    ):
        r = owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "confirm_failed"
    _assert_confirm_enqueue_rollback(world, pay_id, due)


@pytest.mark.django_db
def test_confirm_second_attempt_no_second_receipt(world):
    owner, pay_id, _ = _confirm_flow(world, tid="RCPTTW2")
    assert owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json").status_code == 200
    assert owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json").status_code == 409
    assert (
        OutboundEmail.objects.filter(
            email_type=OutboundEmailType.PAYMENT_RECEIPT,
            business_event_id=f"payment_receipt:{pay_id}",
        ).count()
        == 1
    )


@pytest.mark.django_db(transaction=True)
def test_concurrent_confirm_one_receipt(world):
    owner, pay_id, _ = _confirm_flow(world, tid="RCPTCON1")

    def confirm():
        return owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json").status_code

    results, _ = run_concurrently([confirm, confirm])
    assert Payment.objects.get(pk=pay_id).review_status == ReviewStatus.CONFIRMED
    assert results.count(200) == 1
    assert (
        OutboundEmail.objects.filter(
            business_event_id=f"payment_receipt:{pay_id}",
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_reject_does_not_enqueue_receipt(world):
    owner, pay_id, _ = _confirm_flow(world, tid="RCPTREJ1")
    owner.post(f"/api/payments/{pay_id}/reject/", {"reason": "bad id"}, format="json")
    assert not OutboundEmail.objects.filter(email_type=OutboundEmailType.PAYMENT_RECEIPT).exists()


@pytest.mark.django_db
def test_confirm_non_pending_no_receipt(world):
    owner, pay_id, _ = _confirm_flow(world, tid="RCPTNP01")
    owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    before = OutboundEmail.objects.filter(email_type=OutboundEmailType.PAYMENT_RECEIPT).count()
    payment = Payment.objects.get(pk=pay_id)
    payment.review_status = ReviewStatus.REJECTED
    payment.save(update_fields=["review_status"])
    assert owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json").status_code == 409
    assert OutboundEmail.objects.filter(email_type=OutboundEmailType.PAYMENT_RECEIPT).count() == before


@pytest.mark.django_db
def test_dispatch_success_body(world, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    owner, pay_id, _ = _confirm_flow(world, tid="RCPTDSP1")
    owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    mail.outbox.clear()
    flush_outbound_to_mailbox()
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert "Payment confirmed" in msg.subject
    assert world["plan_x"].plan_name in msg.subject
    assert settings.FRONTEND_BASE_URL in msg.body
    assert f"/app/shared/{world['plan_x'].pk}" in msg.body
    assert f"payment_receipt:{pay_id}" not in msg.body
    assert "payment_id" not in msg.body.lower()


@pytest.mark.django_db
def test_dispatch_usd_plan_note_in_body(world, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    world["plan_x"].currency = "USD"
    world["plan_x"].save(update_fields=["currency"])
    owner, pay_id, _ = _confirm_flow(world, tid="RCPTUSD2")
    owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    mail.outbox.clear()
    flush_outbound_to_mailbox()
    assert "billed in USD" in mail.outbox[0].body


def _receipt_row(world, pay_id):
    row = OutboundEmail.objects.get(business_event_id=f"payment_receipt:{pay_id}")
    claims = claim_batch(batch_size=1, worker_id="pytest-receipt")
    assert claims
    _row_id, token = claims[0]
    return row, token


@pytest.mark.django_db
def test_dispatch_inactive_user_cancelled(world, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    owner, pay_id, _ = _confirm_flow(world, tid="RCPTINAC")
    owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    row, token = _receipt_row(world, pay_id)
    world["member"].is_active = False
    world["member"].save(update_fields=["is_active"])
    with patch("payments.emails.send_payment_receipt_email") as send_mock:
        outcome = process_claimed_row(row_id=row.pk, claim_token=token)
    assert outcome == "cancelled"
    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.CANCELLED
    assert row.last_error_code == "user_inactive"
    send_mock.assert_not_called()


@pytest.mark.django_db
def test_dispatch_unverified_email_cancelled(world, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    owner, pay_id, _ = _confirm_flow(world, tid="RCPTUNVF")
    owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    row, token = _receipt_row(world, pay_id)
    world["member"].email_verified = False
    world["member"].save(update_fields=["email_verified"])
    with patch("payments.emails.send_payment_receipt_email") as send_mock:
        outcome = process_claimed_row(row_id=row.pk, claim_token=token)
    assert outcome == "cancelled"
    row.refresh_from_db()
    assert row.last_error_code == "email_not_verified"
    send_mock.assert_not_called()


@pytest.mark.django_db
def test_dispatch_recipient_mismatch_fails(world, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    owner, pay_id, _ = _confirm_flow(world, tid="RCPTMISM")
    owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    row, token = _receipt_row(world, pay_id)
    row.to_email = "other@example.com"
    row.save(update_fields=["to_email", "updated_at"])
    with patch("payments.emails.send_payment_receipt_email") as send_mock:
        outcome = process_claimed_row(row_id=row.pk, claim_token=token)
    assert outcome == "failed"
    row.refresh_from_db()
    assert row.last_error_code == "recipient_mismatch"
    send_mock.assert_not_called()


@pytest.mark.django_db
def test_dispatch_payment_not_confirmed_cancelled(world, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    owner, pay_id, _ = _confirm_flow(world, tid="RCPTNCFM")
    owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    row, token = _receipt_row(world, pay_id)
    Payment.objects.filter(pk=pay_id).update(review_status=ReviewStatus.REVERSED)
    with patch("payments.emails.send_payment_receipt_email") as send_mock:
        outcome = process_claimed_row(row_id=row.pk, claim_token=token)
    assert outcome == "cancelled"
    row.refresh_from_db()
    assert row.last_error_code == "payment_not_confirmed"
    send_mock.assert_not_called()


@pytest.mark.django_db
def test_dispatch_invalid_payload(world, settings):
    owner, pay_id, _ = _confirm_flow(world, tid="RCPTINPL")
    owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    row = OutboundEmail.objects.get(business_event_id=f"payment_receipt:{pay_id}")
    row.payload = {"payment_id": pay_id, "plan_name": ""}
    row.save(update_fields=["payload", "updated_at"])
    with pytest.raises(OutboxDeliveryError) as exc_info:
        dispatch_outbound_email(row)
    assert exc_info.value.code == "invalid_payload"


@pytest.mark.django_db
def test_unsafe_payload_rejected_at_enqueue(db):
    from accounts.models import User
    from core.models.outbound_email import OutboundEmailType

    user = User.objects.create_user(email="unsafe@example.com", password="pass12345", name="U", email_verified=True)
    bad_url = f"{settings.FRONTEND_BASE_URL}/reset-password?uid=x&token=secret"
    with transaction.atomic():
        with pytest.raises(OutboxPayloadError):
            enqueue_outbound_email(
                email_type=OutboundEmailType.PAYMENT_RECEIPT,
                business_event_id="payment_receipt:999001",
                to_email=user.email,
                user=user,
                payload={
                    "payment_id": 1,
                    "plan_name": "Plan",
                    "subscription_currency": "BDT",
                    "amount": "1.00",
                    "amount_display": "৳1.00",
                    "method": "cash",
                    "method_label": "Cash",
                    "transaction_id": "",
                    "paid_on": "",
                    "confirmed_at": timezone.now().isoformat(),
                    "covered_months": "Jan",
                    "payer_first_name": "U",
                    "confirmer_name": "O",
                    "link_path": bad_url,
                },
            )
    assert not OutboundEmail.objects.filter(business_event_id="payment_receipt:999001").exists()