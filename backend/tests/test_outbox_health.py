"""Read-only outbox health aggregates (Stage 5.3 observability)."""

from __future__ import annotations

import uuid
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from core.mail_enqueue import enqueue_outbound_email
from core.models.outbound_email import OutboundEmail, OutboundEmailStatus, OutboundEmailType
from core.outbox.health import format_health_report, outbox_health_snapshot


@pytest.fixture
def mail_user(db):
    return User.objects.create_user(email="health@example.com", password="pass12345", name="Health")


@pytest.mark.django_db
def test_outbox_health_snapshot_counts_by_status(mail_user):
    with transaction.atomic():
        enqueue_outbound_email(
            email_type=OutboundEmailType.ACCOUNT_VERIFY,
            business_event_id=f"health:{uuid.uuid4()}",
            to_email=mail_user.email,
            user=mail_user,
        )
    snap = outbox_health_snapshot()
    assert snap["status_counts"].get(OutboundEmailStatus.PENDING, 0) >= 1
    assert snap["eligible"] >= 1
    rendered = format_health_report(snap)
    assert "status_pending=" in rendered
    assert mail_user.email not in rendered
    assert "to_email" not in rendered


@pytest.mark.django_db
def test_dry_run_reports_health_without_mutation(mail_user):
    with transaction.atomic():
        row = enqueue_outbound_email(
            email_type=OutboundEmailType.ACCOUNT_VERIFY,
            business_event_id=f"health2:{uuid.uuid4()}",
            to_email=mail_user.email,
            user=mail_user,
        )
    out = StringIO()
    call_command("process_email_outbox", "--dry-run", stdout=out)
    body = out.getvalue()
    assert "eligible=1" in body or "eligible=" in body
    assert "status_pending=" in body
    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.PENDING


@pytest.mark.django_db
def test_stale_processing_lease_counted(mail_user):
    with transaction.atomic():
        row = enqueue_outbound_email(
            email_type=OutboundEmailType.VERIFY_RESEND,
            business_event_id=f"stale:{uuid.uuid4()}",
            to_email=mail_user.email,
            user=mail_user,
        )
    old = timezone.now() - timezone.timedelta(days=2)
    OutboundEmail.objects.filter(pk=row.pk).update(
        status=OutboundEmailStatus.PROCESSING,
        locked_at=old,
        locked_by="stale-lease-test",
    )
    snap = outbox_health_snapshot()
    assert snap["stale_processing_leases"] >= 1