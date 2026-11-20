from __future__ import annotations

import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from core.models.outbound_email import OutboundEmail, OutboundEmailStatus

# Advisory lock distinct from jobs.services run_daily (86420101).
OUTBOX_WORKER_LOCK_ID = 86420102


def eligible_filter(now=None):
    now = now or timezone.now()
    lease_cutoff = now - timedelta(seconds=settings.OUTBOX_LEASE_SECONDS)
    due = Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now)
    active = Q(
        status__in=(OutboundEmailStatus.PENDING, OutboundEmailStatus.RETRY),
    ) & due
    stale_processing = Q(
        status=OutboundEmailStatus.PROCESSING,
        locked_at__isnull=False,
        locked_at__lt=lease_cutoff,
    )
    return active | stale_processing


def count_eligible(*, now=None) -> int:
    return OutboundEmail.objects.filter(eligible_filter(now)).count()


def claim_batch(*, batch_size: int, worker_id: str = "", now=None) -> list[tuple[uuid.UUID, str]]:
    """
    Claim up to batch_size rows in one short transaction.

    Each row receives a unique claim token in ``locked_by`` (32-char hex UUID).
    The optional ``worker_id`` is for operational logging only and is not stored on the row.

    attempt_count is not incremented on claim; it increments when a delivery attempt
    finishes without success (see worker.record_failure).
    """
    del worker_id  # diagnostics only at command layer
    if batch_size < 1:
        return []
    now = now or timezone.now()
    claimed: list[tuple[uuid.UUID, str]] = []
    with transaction.atomic():
        rows = list(
            OutboundEmail.objects.select_for_update(skip_locked=True)
            .filter(eligible_filter(now))
            .order_by(F("next_attempt_at").asc(nulls_first=True), "created_at")[:batch_size]
        )
        for row in rows:
            claim_token = uuid.uuid4().hex
            row.status = OutboundEmailStatus.PROCESSING
            row.locked_at = now
            row.locked_by = claim_token
            row.save(update_fields=["status", "locked_at", "locked_by", "updated_at"])
            claimed.append((row.id, claim_token))
    return claimed


def try_worker_lock() -> bool:
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [OUTBOX_WORKER_LOCK_ID])
        return bool(cursor.fetchone()[0])


def release_worker_lock() -> None:
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_unlock(%s)", [OUTBOX_WORKER_LOCK_ID])