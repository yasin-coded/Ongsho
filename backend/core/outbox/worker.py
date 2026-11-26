"""
Outbox worker orchestration.

Delivery is bounded at-least-once toward the provider, not guaranteed eventual inbox delivery.
A crash after Brevo accepts but before ``sent`` may produce duplicate provider submissions.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.models.outbound_email import OutboundEmail, OutboundEmailStatus
from core.outbox.claim import claim_batch, count_eligible
from core.outbox.dispatch import dispatch_outbound_email
from core.outbox.errors import OutboxDeliveryError, OutboxRetryableError
from core.outbox.retry import classify_send_exception, next_backoff_at

logger = logging.getLogger(__name__)

_CANCEL_ERROR_CODES = frozenset(
    {
        "already_verified",
        "invite_not_pending",
        "invite_expired",
        "invite_token_stale",
        "missing_pending_email",
        "pending_email_mismatch",
        "missing_reminder",
        "opt_out",
        "email_not_verified",
        "invalid_payload",
        "payment_not_confirmed",
        "payment_not_rejected",
        "audit_not_found",
        "email_change_stale",
        "previous_recipient_mismatch",
        "reminder_removed",
        "user_inactive",
        "account_closed",
        "superseded",
    }
)


@dataclass
class WorkerRunResult:
    claimed: int = 0
    sent: int = 0
    retry: int = 0
    failed: int = 0
    cancelled: int = 0
    skipped_ownership: int = 0
    eligible_remaining: int = 0


def process_claimed_row(*, row_id: uuid.UUID, claim_token: str) -> str:
    """
    Deliver one claimed row outside any long DB transaction.

    Returns outcome: sent, retry, failed, cancelled, skipped_ownership.
    """
    row = (
        OutboundEmail.objects.select_related(
            "user",
            "invite__shared_plan__subscription",
            "invite__invited_by",
        )
        .filter(pk=row_id)
        .first()
    )
    if row is None:
        return "skipped_ownership"
    if row.status != OutboundEmailStatus.PROCESSING or row.locked_by != claim_token:
        return "skipped_ownership"

    try:
        dispatch_outbound_email(row)
    except OutboxDeliveryError as exc:
        if exc.permanent:
            if exc.code in _CANCEL_ERROR_CODES:
                _finalize(row_id, claim_token, outcome="cancelled", error_code=exc.code, wipe_secret=True)
                return "cancelled"
            _finalize(row_id, claim_token, outcome="failed", error_code=exc.code, wipe_secret=True)
            return "failed"
        _schedule_retry(row_id, claim_token, error_code=exc.code, retry_after_seconds=getattr(exc, "retry_after_seconds", None))
        return "retry"
    except Exception as exc:
        classified = classify_send_exception(exc)
        if classified.permanent:
            _finalize(row_id, claim_token, outcome="failed", error_code=classified.code)
            return "failed"
        after = getattr(classified, "retry_after_seconds", None)
        _schedule_retry(row_id, claim_token, error_code=classified.code, retry_after_seconds=after)
        return "retry"

    _finalize(row_id, claim_token, outcome="sent", error_code="", wipe_secret=True)
    return "sent"


def _schedule_retry(
    row_id: uuid.UUID,
    claim_token: str,
    *,
    error_code: str,
    retry_after_seconds: int | None,
) -> None:
    with transaction.atomic():
        row = (
            OutboundEmail.objects.select_for_update()
            .filter(pk=row_id, locked_by=claim_token, status=OutboundEmailStatus.PROCESSING)
            .first()
        )
        if row is None:
            return
        row.attempt_count += 1
        if row.attempt_count >= settings.OUTBOUND_EMAIL_MAX_ATTEMPTS:
            row.status = OutboundEmailStatus.FAILED
            row.last_error_code = "max_attempts"
            row.locked_at = None
            row.locked_by = ""
            row.next_attempt_at = None
            row.save(
                update_fields=[
                    "attempt_count",
                    "status",
                    "last_error_code",
                    "locked_at",
                    "locked_by",
                    "next_attempt_at",
                    "updated_at",
                ]
            )
            return
        row.status = OutboundEmailStatus.RETRY
        row.last_error_code = error_code[:64]
        row.next_attempt_at = next_backoff_at(row.attempt_count, retry_after_seconds=retry_after_seconds)
        row.locked_at = None
        row.locked_by = ""
        row.save(
            update_fields=[
                "attempt_count",
                "status",
                "last_error_code",
                "next_attempt_at",
                "locked_at",
                "locked_by",
                "updated_at",
            ]
        )


def _finalize(
    row_id: uuid.UUID,
    claim_token: str,
    *,
    outcome: str,
    error_code: str,
    wipe_secret: bool = False,
) -> None:
    with transaction.atomic():
        row = (
            OutboundEmail.objects.select_for_update()
            .filter(pk=row_id, locked_by=claim_token, status=OutboundEmailStatus.PROCESSING)
            .first()
        )
        if row is None:
            return
        now = timezone.now()
        if outcome == "sent":
            row.status = OutboundEmailStatus.SENT
            row.sent_at = now
            row.last_error_code = ""
            if wipe_secret:
                row.delivery_ciphertext = None
                row.delivery_key_version = None
        elif outcome == "cancelled":
            row.status = OutboundEmailStatus.CANCELLED
            row.last_error_code = error_code[:64]
            if wipe_secret:
                row.delivery_ciphertext = None
                row.delivery_key_version = None
        else:
            row.status = OutboundEmailStatus.FAILED
            row.last_error_code = error_code[:64]
        row.locked_at = None
        row.locked_by = ""
        row.next_attempt_at = None
        update_fields = [
            "status",
            "sent_at",
            "last_error_code",
            "locked_at",
            "locked_by",
            "next_attempt_at",
            "updated_at",
        ]
        if wipe_secret:
            update_fields.extend(["delivery_ciphertext", "delivery_key_version"])
        row.save(update_fields=update_fields)


def run_worker_pass(
    *,
    batch_size: int,
    worker_id: str,
    max_runtime_seconds: float | None = None,
) -> WorkerRunResult:
    """
    Drain eligible rows in batches until empty, partial batch, or max_runtime.

    ``worker_id`` is accepted for API symmetry with the management command but is not
    used for row locks; ``claim_batch`` assigns a unique per-row claim token.
    """
    result = WorkerRunResult()
    deadline = None
    if max_runtime_seconds and max_runtime_seconds > 0:
        deadline = time.monotonic() + max_runtime_seconds

    while True:
        if deadline is not None and time.monotonic() >= deadline:
            break
        if count_eligible() == 0:
            break
        claimed_rows = claim_batch(batch_size=batch_size, worker_id=worker_id)
        if not claimed_rows:
            break
        result.claimed += len(claimed_rows)
        for row_id, claim_token in claimed_rows:
            if deadline is not None and time.monotonic() >= deadline:
                break
            outcome = process_claimed_row(row_id=row_id, claim_token=claim_token)
            if outcome == "sent":
                result.sent += 1
            elif outcome == "retry":
                result.retry += 1
            elif outcome == "failed":
                result.failed += 1
            elif outcome == "cancelled":
                result.cancelled += 1
            else:
                result.skipped_ownership += 1
        if len(claimed_rows) < batch_size:
            break
    result.eligible_remaining = count_eligible()
    return result