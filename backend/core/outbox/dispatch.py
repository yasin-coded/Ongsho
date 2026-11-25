"""
Dispatch outbox rows to Django mail (existing account/sharing email helpers).

At-least-once: provider acceptance via send_mail; not confirmed inbox delivery.
"""

from __future__ import annotations

import logging

from django.contrib.auth.tokens import default_token_generator
from django.utils import timezone
from django.utils.http import int_to_base36

from accounts import emails as account_emails
from core.crypto.invite_delivery import InviteDeliveryDecryptError, decrypt_invite_delivery_secret
from core.models.outbound_email import OutboundEmail, OutboundEmailType
from core.outbox.errors import OutboxDeliveryError
from core.outbox.verification import has_newer_active_verification_row
from sharing import emails as sharing_emails
from sharing.models import InviteStatus
from sharing.services import _invite_link
from sharing.tokens import hash_invite_token

logger = logging.getLogger(__name__)

def dispatch_outbound_email(row: OutboundEmail) -> None:
    """Build and send using verified application email helpers."""
    if row.email_type in (
        OutboundEmailType.ACCOUNT_VERIFY,
        OutboundEmailType.VERIFY_RESEND,
    ):
        _dispatch_account_verify(row)
        return

    if row.email_type == OutboundEmailType.PASSWORD_RESET:
        _dispatch_password_reset(row)
        return

    if row.email_type == OutboundEmailType.EMAIL_CHANGE:
        _dispatch_email_change(row)
        return

    if row.email_type == OutboundEmailType.PLAN_INVITE:
        _dispatch_plan_invite(row)
        return

    if row.email_type == OutboundEmailType.REMINDER:
        _dispatch_reminder(row)
        return

    if row.email_type == OutboundEmailType.PAYMENT_RECEIPT:
        _dispatch_payment_receipt(row)
        return

    if row.email_type == OutboundEmailType.PAYMENT_REJECTED:
        _dispatch_payment_rejected(row)
        return

    if row.email_type == OutboundEmailType.PASSWORD_CHANGED:
        _dispatch_password_changed(row)
        return

    if row.email_type == OutboundEmailType.PASSWORD_RESET_COMPLETED:
        _dispatch_password_reset_completed(row)
        return

    if row.email_type == OutboundEmailType.EMAIL_CHANGED_NEW:
        _dispatch_email_changed_new(row)
        return

    if row.email_type == OutboundEmailType.EMAIL_CHANGED_PREVIOUS:
        _dispatch_email_changed_previous(row)
        return

    raise OutboxDeliveryError("unsupported_type", permanent=True)


def _require_user(row: OutboundEmail):
    user = row.user
    if user is None:
        raise OutboxDeliveryError("missing_user", permanent=True)
    if user.email.lower() != row.to_email.lower():
        raise OutboxDeliveryError("recipient_mismatch", permanent=True)
    return user


def _dispatch_account_verify(row: OutboundEmail) -> None:
    user = _require_user(row)
    if not user.is_active:
        raise OutboxDeliveryError("user_inactive", permanent=True)
    if user.email_verified:
        raise OutboxDeliveryError("already_verified", permanent=True)
    if has_newer_active_verification_row(row):
        raise OutboxDeliveryError("superseded", permanent=True)
    account_emails.send_verification_email(user)


def _dispatch_password_reset(row: OutboundEmail) -> None:
    user = _require_user(row)
    uid = int_to_base36(user.pk)
    token = default_token_generator.make_token(user)
    account_emails.send_password_reset_email(user, uid, token)


def _dispatch_email_change(row: OutboundEmail) -> None:
    user = row.user
    if user is None:
        raise OutboxDeliveryError("missing_user", permanent=True)
    pending = (user.pending_email or "").strip()
    if not pending:
        raise OutboxDeliveryError("missing_pending_email", permanent=True)
    if pending.lower() != row.to_email.strip().lower():
        raise OutboxDeliveryError("pending_email_mismatch", permanent=True)
    account_emails.send_email_change_verification(user, user.pending_email)


_PAYMENT_RECEIPT_PAYLOAD_KEYS = (
    "payment_id",
    "plan_name",
    "amount_display",
    "method_label",
    "covered_months",
    "payer_first_name",
    "confirmer_name",
    "link_path",
)


_SECURITY_NOTICE_PAYLOAD_KEYS = ("event", "user_id", "audit_log_id", "occurred_at", "link_path")


def _dispatch_password_security_notice(
    row: OutboundEmail,
    *,
    expected_audit_action: str,
) -> None:
    user = row.user
    if user is None:
        raise OutboxDeliveryError("missing_user", permanent=True)
    if not user.is_active:
        raise OutboxDeliveryError("user_inactive", permanent=True)
    if not user.email_verified:
        raise OutboxDeliveryError("email_not_verified", permanent=True)
    if user.email.lower() != row.to_email.strip().lower():
        raise OutboxDeliveryError("recipient_mismatch", permanent=True)

    payload = row.payload or {}
    for key in _SECURITY_NOTICE_PAYLOAD_KEYS:
        if payload.get(key) in (None, ""):
            raise OutboxDeliveryError("invalid_payload", permanent=True)

    try:
        audit_log_id = int(payload["audit_log_id"])
        user_id = int(payload["user_id"])
    except (TypeError, ValueError):
        raise OutboxDeliveryError("invalid_payload", permanent=True) from None

    if user_id != user.pk:
        raise OutboxDeliveryError("invalid_payload", permanent=True)

    from audit.models import AuditLog

    if not AuditLog.objects.filter(pk=audit_log_id, user_id=user.pk, action=expected_audit_action).exists():
        raise OutboxDeliveryError("audit_not_found", permanent=True)

    if row.email_type == OutboundEmailType.PASSWORD_CHANGED:
        account_emails.send_password_changed_notice_email(to_email=row.to_email, payload=payload)
        return

    account_emails.send_password_reset_completed_notice_email(to_email=row.to_email, payload=payload)


def _dispatch_password_changed(row: OutboundEmail) -> None:
    _dispatch_password_security_notice(row, expected_audit_action="password.changed")


def _dispatch_password_reset_completed(row: OutboundEmail) -> None:
    _dispatch_password_security_notice(row, expected_audit_action="password.reset_completed")


_EMAIL_CHANGE_COMPLETION_PAYLOAD_KEYS = (
    "event",
    "user_id",
    "audit_log_id",
    "previous_email",
    "new_email",
    "occurred_at",
    "link_path",
)


def _audit_email_from_snapshot(snapshot: dict | None) -> str:
    if not isinstance(snapshot, dict):
        raise OutboxDeliveryError("invalid_payload", permanent=True)
    email = (snapshot.get("email") or "").strip()
    if not email:
        raise OutboxDeliveryError("invalid_payload", permanent=True)
    return email.lower()


def _load_email_change_verified_audit(*, audit_log_id: int, user_id: int):
    from audit.models import AuditLog

    audit = AuditLog.objects.filter(
        pk=audit_log_id,
        user_id=user_id,
        action="email_change.verified",
    ).first()
    if audit is None:
        raise OutboxDeliveryError("audit_not_found", permanent=True)
    return audit


def _validate_email_change_completion_payload(row: OutboundEmail) -> tuple[dict, int, int]:
    payload = row.payload or {}
    for key in _EMAIL_CHANGE_COMPLETION_PAYLOAD_KEYS:
        if payload.get(key) in (None, ""):
            raise OutboxDeliveryError("invalid_payload", permanent=True)
    try:
        audit_log_id = int(payload["audit_log_id"])
        user_id = int(payload["user_id"])
    except (TypeError, ValueError):
        raise OutboxDeliveryError("invalid_payload", permanent=True) from None
    return payload, audit_log_id, user_id


def _dispatch_email_changed_new(row: OutboundEmail) -> None:
    user = row.user
    if user is None:
        raise OutboxDeliveryError("missing_user", permanent=True)
    if not user.is_active:
        raise OutboxDeliveryError("user_inactive", permanent=True)
    if not user.email_verified:
        raise OutboxDeliveryError("email_not_verified", permanent=True)
    if user.email.lower() != row.to_email.strip().lower():
        raise OutboxDeliveryError("recipient_mismatch", permanent=True)

    payload, audit_log_id, user_id = _validate_email_change_completion_payload(row)
    if user_id != user.pk:
        raise OutboxDeliveryError("invalid_payload", permanent=True)

    audit = _load_email_change_verified_audit(audit_log_id=audit_log_id, user_id=user.pk)
    audit_old = _audit_email_from_snapshot(audit.old_value)
    audit_new = _audit_email_from_snapshot(audit.new_value)
    payload_previous = str(payload["previous_email"]).strip().lower()
    payload_new = str(payload["new_email"]).strip().lower()
    if audit_old != payload_previous or audit_new != payload_new:
        raise OutboxDeliveryError("invalid_payload", permanent=True)
    if user.email.lower() != audit_new or user.email.lower() != payload_new:
        raise OutboxDeliveryError("email_change_stale", permanent=True)

    account_emails.send_email_changed_new_notice_email(to_email=row.to_email, payload=payload)


def _dispatch_email_changed_previous(row: OutboundEmail) -> None:
    user = row.user
    if user is None:
        raise OutboxDeliveryError("missing_user", permanent=True)
    if not user.is_active:
        raise OutboxDeliveryError("user_inactive", permanent=True)

    payload, audit_log_id, user_id = _validate_email_change_completion_payload(row)
    if user_id != user.pk:
        raise OutboxDeliveryError("invalid_payload", permanent=True)

    audit = _load_email_change_verified_audit(audit_log_id=audit_log_id, user_id=user.pk)
    audit_old = _audit_email_from_snapshot(audit.old_value)
    audit_new = _audit_email_from_snapshot(audit.new_value)
    row_previous = row.to_email.strip().lower()
    payload_previous = str(payload["previous_email"]).strip().lower()

    if row_previous != audit_old or row_previous != payload_previous:
        raise OutboxDeliveryError("previous_recipient_mismatch", permanent=True)
    if user.email.lower() != audit_new:
        raise OutboxDeliveryError("email_change_stale", permanent=True)

    account_emails.send_email_changed_previous_notice_email(to_email=row.to_email, payload=payload)


def _dispatch_payment_receipt(row: OutboundEmail) -> None:
    user = row.user
    if user is None:
        raise OutboxDeliveryError("missing_user", permanent=True)
    if not user.is_active:
        raise OutboxDeliveryError("user_inactive", permanent=True)
    if not user.email_verified:
        raise OutboxDeliveryError("email_not_verified", permanent=True)
    if user.email.lower() != row.to_email.strip().lower():
        raise OutboxDeliveryError("recipient_mismatch", permanent=True)

    payload = row.payload or {}
    payment_id = payload.get("payment_id")
    if payment_id is None:
        raise OutboxDeliveryError("invalid_payload", permanent=True)
    try:
        payment_pk = int(payment_id)
    except (TypeError, ValueError):
        raise OutboxDeliveryError("invalid_payload", permanent=True) from None

    from payments.models import Payment, ReviewStatus

    payment = Payment.objects.filter(pk=payment_pk).first()
    if payment is None or payment.review_status != ReviewStatus.CONFIRMED:
        raise OutboxDeliveryError("payment_not_confirmed", permanent=True)

    for key in _PAYMENT_RECEIPT_PAYLOAD_KEYS:
        if not str(payload.get(key) or "").strip():
            raise OutboxDeliveryError("invalid_payload", permanent=True)

    from payments import emails as payment_emails

    payment_emails.send_payment_receipt_email(to_email=row.to_email, payload=payload)


_PAYMENT_REJECTION_PAYLOAD_KEYS = (
    "payment_id",
    "user_id",
    "audit_log_id",
    "plan_name",
    "amount_display",
    "method_label",
    "rejection_reason",
    "reviewer_name",
    "reviewed_at",
    "payer_first_name",
    "link_path",
)


def _dispatch_payment_rejected(row: OutboundEmail) -> None:
    user = row.user
    if user is None:
        raise OutboxDeliveryError("missing_user", permanent=True)
    if not user.is_active:
        raise OutboxDeliveryError("user_inactive", permanent=True)
    if not user.email_verified:
        raise OutboxDeliveryError("email_not_verified", permanent=True)
    if user.email.lower() != row.to_email.strip().lower():
        raise OutboxDeliveryError("recipient_mismatch", permanent=True)

    payload = row.payload or {}
    if payload.get("payment_id") is None or payload.get("audit_log_id") is None or payload.get("user_id") is None:
        raise OutboxDeliveryError("invalid_payload", permanent=True)
    try:
        payment_pk = int(payload["payment_id"])
        audit_log_id = int(payload["audit_log_id"])
        user_id = int(payload["user_id"])
    except (TypeError, ValueError):
        raise OutboxDeliveryError("invalid_payload", permanent=True) from None

    if user_id != user.pk:
        raise OutboxDeliveryError("invalid_payload", permanent=True)

    for key in _PAYMENT_REJECTION_PAYLOAD_KEYS:
        if not str(payload.get(key) or "").strip():
            raise OutboxDeliveryError("invalid_payload", permanent=True)

    from audit.models import AuditLog
    from payments.models import Payment, ReviewStatus

    payment = Payment.objects.select_related("member").filter(pk=payment_pk).first()
    if payment is None or payment.review_status != ReviewStatus.REJECTED:
        raise OutboxDeliveryError("payment_not_rejected", permanent=True)
    if payment.member.user_id != user.pk:
        raise OutboxDeliveryError("invalid_payload", permanent=True)

    audit = AuditLog.objects.filter(
        pk=audit_log_id,
        action="payment.rejected",
        entity_type="Payment",
        entity_id=payment_pk,
    ).first()
    if audit is None:
        raise OutboxDeliveryError("audit_not_found", permanent=True)

    audit_reason = str((audit.new_value or {}).get("reason") or "").strip()
    payload_reason = str(payload.get("rejection_reason") or "").strip()
    if audit_reason != payload_reason:
        raise OutboxDeliveryError("invalid_payload", permanent=True)

    from payments import emails as payment_emails

    payment_emails.send_payment_rejected_email(to_email=row.to_email, payload=payload)


def _dispatch_reminder(row: OutboundEmail) -> None:
    if row.reminder_id is None:
        raise OutboxDeliveryError("missing_reminder", permanent=True)
    from notifications.models import Reminder

    if not Reminder.objects.filter(pk=row.reminder_id).exists():
        raise OutboxDeliveryError("missing_reminder", permanent=True)
    user = _require_user(row)
    if not user.email_reminders:
        raise OutboxDeliveryError("opt_out", permanent=True)
    if not user.email_verified:
        raise OutboxDeliveryError("email_not_verified", permanent=True)
    payload = row.payload or {}
    title = str(payload.get("title") or "").strip()
    message = str(payload.get("message") or "").strip()
    link_path = str(payload.get("link_path") or "").strip()
    if not title or not message or not link_path:
        raise OutboxDeliveryError("invalid_payload", permanent=True)
    from notifications.emails import send_reminder_email

    send_reminder_email(
        to_email=row.to_email,
        subject=title,
        message=message,
        link_path=link_path,
    )


def _dispatch_plan_invite(row: OutboundEmail) -> None:
    invite = row.invite
    if invite is None:
        raise OutboxDeliveryError("missing_invite", permanent=True)
    now = timezone.now()
    if invite.status != InviteStatus.PENDING:
        raise OutboxDeliveryError("invite_not_pending", permanent=True)
    if invite.expires_on <= now:
        raise OutboxDeliveryError("invite_expired", permanent=True)
    if row.delivery_ciphertext is None or row.delivery_key_version is None:
        raise OutboxDeliveryError("missing_delivery_secret", permanent=True)
    try:
        raw = decrypt_invite_delivery_secret(
            bytes(row.delivery_ciphertext),
            version=row.delivery_key_version,
        )
    except InviteDeliveryDecryptError as exc:
        raise OutboxDeliveryError("decrypt_failed", permanent=True) from exc
    if hash_invite_token(raw) != invite.token_hash:
        raise OutboxDeliveryError("invite_token_stale", permanent=True)

    subscription = invite.shared_plan.subscription
    plan_name = subscription.plan_name or "your plan"
    inviter_name = invite.invited_by.name or invite.invited_by.email
    sharing_emails.send_invite_email(
        to_email=row.to_email,
        plan_name=plan_name,
        inviter_name=inviter_name,
        invite_link=_invite_link(raw),
    )