"""
Verification email outbox helpers (account_verify, verify_resend).

Enqueue cancels only pending/retry siblings — not processing rows, which may be mid-send outside DB.
Dispatch may still cancel an older row when a newer active row exists (including processing).
A narrow race remains: a newer row may be enqueued after dispatch checks but before the provider accepts.
"""

from __future__ import annotations

from django.db.models import Q

from core.models.outbound_email import OutboundEmail, OutboundEmailStatus, OutboundEmailType

VERIFICATION_EMAIL_TYPES = (
    OutboundEmailType.ACCOUNT_VERIFY,
    OutboundEmailType.VERIFY_RESEND,
)

# Enqueue-time supersession: never touch processing (worker may be in flight to provider).
_ENQUEUE_CANCEL_STATUSES = (
    OutboundEmailStatus.PENDING,
    OutboundEmailStatus.RETRY,
)

# Dispatch-time supersession: include processing so reclaimed/stale sends defer to newer work.
_DISPATCH_SUPERSEDE_STATUSES = (
    OutboundEmailStatus.PENDING,
    OutboundEmailStatus.RETRY,
    OutboundEmailStatus.PROCESSING,
)


def cancel_pending_verification_deliveries(user_id: int) -> int:
    """
    Cancel pending/retry verification outbox rows for a user inside the caller transaction.

    Caller must hold transaction.atomic(); rows are locked with select_for_update.
    """
    count = 0
    rows = OutboundEmail.objects.select_for_update().filter(
        user_id=user_id,
        email_type__in=VERIFICATION_EMAIL_TYPES,
        status__in=_ENQUEUE_CANCEL_STATUSES,
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


def has_newer_active_verification_row(row: OutboundEmail) -> bool:
    """True when another verification row for the same user is newer by (created_at, id)."""
    if row.user_id is None:
        return False
    return (
        OutboundEmail.objects.filter(
            user_id=row.user_id,
            email_type__in=VERIFICATION_EMAIL_TYPES,
            status__in=_DISPATCH_SUPERSEDE_STATUSES,
        )
        .filter(
            Q(created_at__gt=row.created_at)
            | Q(created_at=row.created_at, id__gt=row.id),
        )
        .exclude(pk=row.pk)
        .exists()
    )