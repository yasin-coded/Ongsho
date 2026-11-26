"""Read-only OutboundEmail aggregates for operators (no PII, no row payloads)."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Min
from django.utils import timezone

from core.models.outbound_email import OutboundEmail, OutboundEmailStatus
from core.outbox.claim import eligible_filter


def outbox_health_snapshot(*, now=None) -> dict:
    now = now or timezone.now()
    lease_cutoff = now - timedelta(seconds=settings.OUTBOX_LEASE_SECONDS)

    base = OutboundEmail.objects.all()
    status_rows = base.values("status").annotate(count=Count("id")).order_by("status")
    status_counts = {row["status"]: row["count"] for row in status_rows}

    processing = OutboundEmail.objects.filter(status=OutboundEmailStatus.PROCESSING)
    stale_processing = processing.filter(locked_at__isnull=False, locked_at__lt=lease_cutoff).count()
    active_processing = max(0, processing.count() - stale_processing)

    backlog_statuses = (OutboundEmailStatus.PENDING, OutboundEmailStatus.RETRY)
    oldest_backlog = (
        OutboundEmail.objects.filter(status__in=backlog_statuses)
        .aggregate(oldest=Min("created_at"))
        .get("oldest")
    )
    oldest_processing = processing.aggregate(oldest=Min("locked_at")).get("oldest")

    eligible = OutboundEmail.objects.filter(eligible_filter(now)).count()

    type_rows = (
        OutboundEmail.objects.filter(status__in=backlog_statuses + (OutboundEmailStatus.PROCESSING,))
        .values("email_type")
        .annotate(count=Count("id"))
        .order_by("-count", "email_type")[:20]
    )
    backlog_by_type = {row["email_type"]: row["count"] for row in type_rows}

    return {
        "as_of": now.isoformat(),
        "status_counts": status_counts,
        "eligible": eligible,
        "stale_processing_leases": stale_processing,
        "active_processing": active_processing,
        "oldest_pending_or_retry_at": oldest_backlog.isoformat() if oldest_backlog else None,
        "oldest_processing_locked_at": oldest_processing.isoformat() if oldest_processing else None,
        "backlog_by_email_type": backlog_by_type,
        "lease_seconds": settings.OUTBOX_LEASE_SECONDS,
    }


def format_health_report(snapshot: dict, *, eligible: int | None = None) -> str:
    """Key=value lines safe for logs and GitHub Actions output."""
    lines = [
        f"eligible={eligible if eligible is not None else snapshot.get('eligible', 0)}",
        f"stale_processing_leases={snapshot['stale_processing_leases']}",
        f"active_processing={snapshot['active_processing']}",
    ]
    for status in (
        OutboundEmailStatus.PENDING,
        OutboundEmailStatus.RETRY,
        OutboundEmailStatus.PROCESSING,
        OutboundEmailStatus.SENT,
        OutboundEmailStatus.FAILED,
        OutboundEmailStatus.CANCELLED,
    ):
        lines.append(f"status_{status}={snapshot['status_counts'].get(status, 0)}")
    if snapshot.get("oldest_pending_or_retry_at"):
        lines.append(f"oldest_backlog_at={snapshot['oldest_pending_or_retry_at']}")
    if snapshot.get("oldest_processing_locked_at"):
        lines.append(f"oldest_processing_at={snapshot['oldest_processing_locked_at']}")
    types = snapshot.get("backlog_by_email_type") or {}
    if types:
        type_bits = ",".join(f"{k}:{v}" for k, v in sorted(types.items()))
        lines.append(f"backlog_by_type={type_bits}")
    return "\n".join(lines)