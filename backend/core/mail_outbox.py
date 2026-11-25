"""Outbox enqueue helpers for domain services (call only inside transaction.atomic)."""

from __future__ import annotations

import uuid

from core.mail_enqueue import OutboxPayloadError, enqueue_outbound_email
from core.models.outbound_email import OutboundEmail, OutboundEmailStatus, OutboundEmailType
from core.outbox.verification import cancel_pending_verification_deliveries

_ACTIVE_DELIVERY = (
    OutboundEmailStatus.PENDING,
    OutboundEmailStatus.PROCESSING,
    OutboundEmailStatus.RETRY,
)


def enqueue_account_verify(user, *, business_event_id: str | None = None) -> OutboundEmail:
    cancel_pending_verification_deliveries(user.pk)
    return enqueue_outbound_email(
        email_type=OutboundEmailType.ACCOUNT_VERIFY,
        business_event_id=business_event_id or f"account_verify:register:{user.pk}",
        to_email=user.email,
        user=user,
    )


def enqueue_verify_resend(user) -> OutboundEmail:
    cancel_pending_verification_deliveries(user.pk)
    return enqueue_outbound_email(
        email_type=OutboundEmailType.VERIFY_RESEND,
        business_event_id=f"verify_resend:{uuid.uuid4()}",
        to_email=user.email,
        user=user,
    )


def enqueue_password_reset(user) -> OutboundEmail:
    return enqueue_outbound_email(
        email_type=OutboundEmailType.PASSWORD_RESET,
        business_event_id=f"password_reset:{user.pk}:{uuid.uuid4()}",
        to_email=user.email,
        user=user,
    )


def enqueue_email_change(user, *, business_event_id: str | None = None) -> OutboundEmail:
    pending = (user.pending_email or "").strip()
    return enqueue_outbound_email(
        email_type=OutboundEmailType.EMAIL_CHANGE,
        business_event_id=business_event_id or f"email_change:{user.pk}:{uuid.uuid4()}",
        to_email=pending,
        user=user,
    )


_EMAIL_CHANGE_CANCEL_STATUSES = (
    OutboundEmailStatus.PENDING,
    OutboundEmailStatus.RETRY,
)

_ACCOUNT_CLOSURE_NOTIFICATION_TYPES = (
    OutboundEmailType.EMAIL_CHANGED_NEW,
    OutboundEmailType.EMAIL_CHANGED_PREVIOUS,
    OutboundEmailType.PASSWORD_CHANGED,
    OutboundEmailType.PASSWORD_RESET_COMPLETED,
    OutboundEmailType.PAYMENT_REJECTED,
)


def cancel_pending_account_notification_deliveries(user_id: int) -> int:
    """
    Cancel pending/retry account-security and payment-notification rows on account closure.

    Caller must hold transaction.atomic(); rows are locked with select_for_update.
    Does not cancel processing rows (worker may be in flight to the provider).
    """
    count = 0
    rows = OutboundEmail.objects.select_for_update().filter(
        user_id=user_id,
        email_type__in=_ACCOUNT_CLOSURE_NOTIFICATION_TYPES,
        status__in=_EMAIL_CHANGE_CANCEL_STATUSES,
    )
    for row in rows:
        row.status = OutboundEmailStatus.CANCELLED
        row.last_error_code = "account_closed"
        row.locked_at = None
        row.locked_by = ""
        row.next_attempt_at = None
        row.save(
            update_fields=[
                "status",
                "last_error_code",
                "locked_at",
                "locked_by",
                "next_attempt_at",
                "updated_at",
            ]
        )
        count += 1
    return count


def cancel_pending_email_change_deliveries(user_id: int) -> int:
    """Cancel pending/retry email-change outbox rows for a user (caller must hold transaction.atomic)."""
    count = 0
    rows = OutboundEmail.objects.select_for_update().filter(
        user_id=user_id,
        email_type=OutboundEmailType.EMAIL_CHANGE,
        status__in=_EMAIL_CHANGE_CANCEL_STATUSES,
    )
    for row in rows:
        row.status = OutboundEmailStatus.CANCELLED
        row.last_error_code = "superseded"
        row.locked_at = None
        row.locked_by = ""
        row.next_attempt_at = None
        row.save(
            update_fields=[
                "status",
                "last_error_code",
                "locked_at",
                "locked_by",
                "next_attempt_at",
                "updated_at",
            ]
        )
        count += 1
    return count


def cancel_pending_invite_deliveries(invite_id: int) -> int:
    """Cancel active plan_invite rows for an invite (caller must hold transaction.atomic)."""
    count = 0
    rows = OutboundEmail.objects.select_for_update().filter(
        invite_id=invite_id,
        email_type=OutboundEmailType.PLAN_INVITE,
        status__in=_ACTIVE_DELIVERY,
    )
    for row in rows:
        row.status = OutboundEmailStatus.CANCELLED
        row.last_error_code = "superseded"
        row.delivery_ciphertext = None
        row.delivery_key_version = None
        row.locked_at = None
        row.locked_by = ""
        row.next_attempt_at = None
        row.save(
            update_fields=[
                "status",
                "last_error_code",
                "delivery_ciphertext",
                "delivery_key_version",
                "locked_at",
                "locked_by",
                "next_attempt_at",
                "updated_at",
            ]
        )
        count += 1
    return count


def purge_outbound_emails_for_invites(invite_ids) -> int:
    """Delete plan_invite outbox rows before invite rows are removed (FK SET_NULL violates integrity checks)."""
    if not invite_ids:
        return 0
    deleted, _ = OutboundEmail.objects.filter(invite_id__in=invite_ids).delete()
    return deleted


def enqueue_reminder_delivery(
    *,
    reminder,
    user,
    title: str,
    message: str,
    link_path: str,
) -> OutboundEmail:
    """Queue one optional reminder email; caller must be inside transaction.atomic."""
    return enqueue_outbound_email(
        email_type=OutboundEmailType.REMINDER,
        business_event_id=f"reminder:{reminder.pk}",
        to_email=user.email,
        user=user,
        reminder=reminder,
        payload={
            "title": title,
            "message": message,
            "link_path": link_path,
        },
    )


def cancel_pending_reminder_deliveries_for_user(user_id: int) -> int:
    """Cancel active reminder outbox rows when the user opts out of email reminders."""
    count = 0
    rows = OutboundEmail.objects.select_for_update().filter(
        user_id=user_id,
        email_type=OutboundEmailType.REMINDER,
        status__in=_ACTIVE_DELIVERY,
    )
    for row in rows:
        row.status = OutboundEmailStatus.CANCELLED
        row.last_error_code = "opt_out"
        row.locked_at = None
        row.locked_by = ""
        row.next_attempt_at = None
        row.save(
            update_fields=[
                "status",
                "last_error_code",
                "locked_at",
                "locked_by",
                "next_attempt_at",
                "updated_at",
            ]
        )
        count += 1
    return count


def enqueue_plan_invite_delivery(*, invite, raw_token: str, business_event_id: str) -> OutboundEmail:
    return enqueue_outbound_email(
        email_type=OutboundEmailType.PLAN_INVITE,
        business_event_id=business_event_id,
        to_email=invite.email,
        invite=invite,
        invite_delivery_secret=raw_token,
    )


_REQUIRED_RECEIPT_PAYLOAD_KEYS = (
    "payment_id",
    "plan_name",
    "subscription_currency",
    "amount",
    "amount_display",
    "method",
    "method_label",
    "transaction_id",
    "paid_on",
    "confirmed_at",
    "covered_months",
    "payer_first_name",
    "confirmer_name",
    "link_path",
)


def enqueue_payment_receipt(*, payment, confirmed_by) -> OutboundEmail:
    """Queue a payment receipt for the payer; caller must be inside transaction.atomic."""
    from core.choices import Currency
    from core.money import format_bdt
    from payments.services import _covered_months, _first_name, _method_label

    payer = payment.member.user
    sub = payment.shared_plan.subscription
    payload = {
        "payment_id": payment.pk,
        "plan_name": sub.plan_name or "",
        "subscription_currency": sub.currency,
        "amount": str(payment.amount),
        "amount_display": format_bdt(payment.amount),
        "method": payment.method,
        "method_label": _method_label(payment.method),
        "transaction_id": payment.transaction_id or "",
        "paid_on": payment.paid_on.isoformat() if payment.paid_on else "",
        "confirmed_at": payment.reviewed_at.isoformat() if payment.reviewed_at else "",
        "covered_months": _covered_months(payment),
        "payer_first_name": _first_name(payer),
        "confirmer_name": _first_name(confirmed_by),
        "link_path": f"/app/shared/{sub.pk}",
    }
    if sub.currency not in (Currency.BDT, Currency.USD):
        payload["subscription_currency"] = str(sub.currency)
    for key in _REQUIRED_RECEIPT_PAYLOAD_KEYS:
        if key not in payload:
            raise OutboxPayloadError(f"payment receipt payload missing {key}")
    return enqueue_outbound_email(
        email_type=OutboundEmailType.PAYMENT_RECEIPT,
        business_event_id=f"payment_receipt:{payment.pk}",
        to_email=payer.email,
        user=payer,
        payload=payload,
    )


_REQUIRED_REJECTION_PAYLOAD_KEYS = (
    "payment_id",
    "user_id",
    "audit_log_id",
    "plan_name",
    "subscription_currency",
    "amount_display",
    "method_label",
    "rejection_reason",
    "reviewer_name",
    "reviewed_at",
    "payer_first_name",
    "link_path",
)


def enqueue_payment_rejection(
    *,
    payment,
    rejected_by,
    audit_log_id: int,
    rejection_reason: str,
) -> OutboundEmail:
    """Queue a payment-rejection notice for the payer; caller must be inside transaction.atomic."""
    from core.choices import Currency
    from core.money import format_bdt
    from payments.services import _first_name, _method_label

    payer = payment.member.user
    sub = payment.shared_plan.subscription
    payload = {
        "payment_id": payment.pk,
        "user_id": payer.pk,
        "audit_log_id": audit_log_id,
        "plan_name": sub.plan_name or "",
        "subscription_currency": sub.currency,
        "amount_display": format_bdt(payment.amount),
        "method_label": _method_label(payment.method),
        "transaction_id": payment.transaction_id or "",
        "paid_on": payment.paid_on.isoformat() if payment.paid_on else "",
        "rejection_reason": rejection_reason.strip(),
        "reviewer_name": _first_name(rejected_by),
        "reviewed_at": payment.reviewed_at.isoformat() if payment.reviewed_at else "",
        "payer_first_name": _first_name(payer),
        "link_path": f"/app/shared/{sub.pk}",
    }
    if sub.currency not in (Currency.BDT, Currency.USD):
        payload["subscription_currency"] = str(sub.currency)
    for key in _REQUIRED_REJECTION_PAYLOAD_KEYS:
        if key not in payload or not str(payload[key]).strip():
            raise OutboxPayloadError(f"payment rejection payload missing {key}")
    return enqueue_outbound_email(
        email_type=OutboundEmailType.PAYMENT_REJECTED,
        business_event_id=f"payment_rejected:{audit_log_id}",
        to_email=payer.email,
        user=payer,
        payload=payload,
    )


def _password_security_payload(*, user, audit_log_id: int, event: str) -> dict:
    from django.utils import timezone

    return {
        "event": event,
        "user_id": user.pk,
        "audit_log_id": audit_log_id,
        "occurred_at": timezone.now().isoformat(),
        "link_path": "/app/profile",
    }


def enqueue_password_changed_notice(*, user, audit_log_id: int) -> OutboundEmail:
    """Queue a password-changed security notice; caller must be inside transaction.atomic."""
    return enqueue_outbound_email(
        email_type=OutboundEmailType.PASSWORD_CHANGED,
        business_event_id=f"password_changed:{audit_log_id}",
        to_email=user.email,
        user=user,
        payload=_password_security_payload(
            user=user,
            audit_log_id=audit_log_id,
            event=OutboundEmailType.PASSWORD_CHANGED,
        ),
    )


def enqueue_password_reset_completed_notice(*, user, audit_log_id: int) -> OutboundEmail:
    """Queue a password-reset-completed security notice; caller must be inside transaction.atomic."""
    return enqueue_outbound_email(
        email_type=OutboundEmailType.PASSWORD_RESET_COMPLETED,
        business_event_id=f"password_reset_completed:{audit_log_id}",
        to_email=user.email,
        user=user,
        payload=_password_security_payload(
            user=user,
            audit_log_id=audit_log_id,
            event=OutboundEmailType.PASSWORD_RESET_COMPLETED,
        ),
    )


def _email_change_completion_payload(
    *,
    user,
    audit_log_id: int,
    event: str,
    previous_email: str,
    new_email: str,
) -> dict:
    from django.utils import timezone

    return {
        "event": event,
        "user_id": user.pk,
        "audit_log_id": audit_log_id,
        "previous_email": previous_email.strip().lower(),
        "new_email": new_email.strip().lower(),
        "occurred_at": timezone.now().isoformat(),
        "link_path": "/app/profile",
    }


def enqueue_email_changed_new_notice(
    *,
    user,
    audit_log_id: int,
    previous_email: str,
    new_email: str,
) -> OutboundEmail:
    """Queue confirmation to the new address after email change verification."""
    return enqueue_outbound_email(
        email_type=OutboundEmailType.EMAIL_CHANGED_NEW,
        business_event_id=f"email_changed_new:{audit_log_id}",
        to_email=new_email,
        user=user,
        payload=_email_change_completion_payload(
            user=user,
            audit_log_id=audit_log_id,
            event=OutboundEmailType.EMAIL_CHANGED_NEW,
            previous_email=previous_email,
            new_email=new_email,
        ),
    )


def enqueue_email_changed_previous_notice(
    *,
    user,
    audit_log_id: int,
    previous_email: str,
    new_email: str,
) -> OutboundEmail:
    """Queue security warning to the previous address after email change verification."""
    return enqueue_outbound_email(
        email_type=OutboundEmailType.EMAIL_CHANGED_PREVIOUS,
        business_event_id=f"email_changed_previous:{audit_log_id}",
        to_email=previous_email,
        user=user,
        payload=_email_change_completion_payload(
            user=user,
            audit_log_id=audit_log_id,
            event=OutboundEmailType.EMAIL_CHANGED_PREVIOUS,
            previous_email=previous_email,
            new_email=new_email,
        ),
    )
