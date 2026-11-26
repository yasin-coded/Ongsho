"""Management command tests for process_email_outbox."""

from __future__ import annotations

import uuid
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import CommandError, call_command
from django.db import connection, transaction

from accounts.models import User
from core.mail_enqueue import enqueue_outbound_email
from core.models.outbound_email import OutboundEmailStatus, OutboundEmailType
from core.outbox.claim import OUTBOX_WORKER_LOCK_ID
from core.outbox.worker import WorkerRunResult


def _enqueue_pending(user):
    with transaction.atomic():
        return enqueue_outbound_email(
            email_type=OutboundEmailType.ACCOUNT_VERIFY,
            business_event_id=f"cmd:{uuid.uuid4()}",
            to_email=user.email,
            user=user,
        )


@pytest.mark.django_db
def test_dry_run_counts_eligible_only(mail_user):
    with transaction.atomic():
        _enqueue_pending(mail_user)
    out = StringIO()
    call_command("process_email_outbox", "--dry-run", stdout=out)
    assert "eligible=1" in out.getvalue()


@pytest.mark.django_db
def test_dry_run_does_not_claim(mail_user):
    with transaction.atomic():
        row = _enqueue_pending(mail_user)
    out = StringIO()
    call_command("process_email_outbox", "--dry-run", stdout=out)
    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.PENDING


@pytest.mark.django_db
def test_default_args_invoke_worker_pass(mail_user):
    with transaction.atomic():
        _enqueue_pending(mail_user)
    result = WorkerRunResult(claimed=1, sent=1)
    with patch(
        "core.management.commands.process_email_outbox.try_worker_lock",
        return_value=True,
    ):
        with patch(
            "core.management.commands.process_email_outbox.release_worker_lock",
        ) as release_mock:
            with patch(
                "core.management.commands.process_email_outbox.run_worker_pass",
                return_value=result,
            ) as run_mock:
                out = StringIO()
                call_command("process_email_outbox", stdout=out)
    run_mock.assert_called_once()
    kwargs = run_mock.call_args.kwargs
    assert kwargs["batch_size"] == 50
    assert kwargs["max_runtime_seconds"] is None
    assert "worker_id" in kwargs and kwargs["worker_id"]
    assert "claimed=1" in out.getvalue() or "claimed=" in out.getvalue()
    release_mock.assert_called_once()


@pytest.mark.django_db
def test_explicit_batch_size_and_max_runtime(mail_user):
    result = WorkerRunResult()
    with patch(
        "core.management.commands.process_email_outbox.try_worker_lock",
        return_value=True,
    ):
        with patch("core.management.commands.process_email_outbox.release_worker_lock"):
            with patch(
                "core.management.commands.process_email_outbox.run_worker_pass",
                return_value=result,
            ) as run_mock:
                call_command(
                    "process_email_outbox",
                    "--batch-size=7",
                    "--max-runtime=55",
                    "--worker-id=ops-cron-1",
                )
    assert run_mock.call_args.kwargs["batch_size"] == 7
    assert run_mock.call_args.kwargs["max_runtime_seconds"] == 55.0
    assert run_mock.call_args.kwargs["worker_id"] == "ops-cron-1"


@pytest.mark.django_db
def test_stdout_summary_shape():
    result = WorkerRunResult(claimed=2, sent=1, retry=1, failed=0, cancelled=0, skipped_ownership=0)
    with patch(
        "core.management.commands.process_email_outbox.try_worker_lock",
        return_value=True,
    ):
        with patch("core.management.commands.process_email_outbox.release_worker_lock"):
            with patch(
                "core.management.commands.process_email_outbox.run_worker_pass",
                return_value=result,
            ):
                out = StringIO()
                call_command("process_email_outbox", "--worker-id=test-worker", stdout=out)
    text = out.getvalue()
    assert "worker_id=test-worker" in text
    assert "claimed=2" in text
    assert "sent=1" in text
    assert "retry=1" in text
    assert "duration_seconds=" in text
    assert "exit_ok=true" in text


@pytest.mark.django_db
def test_advisory_lock_busy_skips_worker():
    with patch(
        "core.management.commands.process_email_outbox.try_worker_lock",
        return_value=False,
    ):
        with patch(
            "core.management.commands.process_email_outbox.run_worker_pass",
        ) as run_mock:
            out = StringIO()
            call_command("process_email_outbox", stdout=out)
    run_mock.assert_not_called()
    assert "advisory_lock=busy" in out.getvalue()
    assert "exit_ok=true" in out.getvalue()


@pytest.mark.django_db
def test_exception_still_releases_lock():
    with patch(
        "core.management.commands.process_email_outbox.try_worker_lock",
        return_value=True,
    ):
        with patch(
            "core.management.commands.process_email_outbox.release_worker_lock",
        ) as release_mock:
            with patch(
                "core.management.commands.process_email_outbox.run_worker_pass",
                side_effect=RuntimeError("boom"),
            ):
                with pytest.raises(CommandError, match="operational failure"):
                    call_command("process_email_outbox")
    release_mock.assert_called_once()


@pytest.mark.django_db
def test_no_advisory_lock_bypasses_acquire():
    with patch(
        "core.management.commands.process_email_outbox.try_worker_lock",
    ) as lock_mock:
        with patch("core.management.commands.process_email_outbox.release_worker_lock") as release_mock:
            with patch(
                "core.management.commands.process_email_outbox.run_worker_pass",
                return_value=WorkerRunResult(),
            ):
                call_command("process_email_outbox", "--no-advisory-lock")
    lock_mock.assert_not_called()
    release_mock.assert_not_called()


@pytest.mark.django_db
def test_invalid_batch_size_raises():
    with pytest.raises(CommandError, match="batch-size"):
        call_command("process_email_outbox", "--batch-size=0")


@pytest.mark.django_db
@pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="PostgreSQL session advisory locks are not available on this database",
)
def test_postgresql_advisory_lock_acquire_and_release_integration():
    """Same-session acquire/release round trip on PostgreSQL (not cross-session overlap)."""
    from core.outbox.claim import release_worker_lock, try_worker_lock

    assert try_worker_lock() is True
    release_worker_lock()
    assert try_worker_lock() is True
    release_worker_lock()


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="PostgreSQL session advisory locks are not available on this database",
)
def test_postgresql_advisory_lock_second_session_busy():
    """A separate DB session cannot acquire the lock while the first holds it."""
    from django.db import connections

    from core.outbox.claim import release_worker_lock, try_worker_lock

    assert try_worker_lock() is True
    try:
        other = connections.create_connection("default")
        try:
            with other.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(%s)", [OUTBOX_WORKER_LOCK_ID])
                assert cursor.fetchone()[0] is False
        finally:
            other.close()
    finally:
        release_worker_lock()


@pytest.fixture
def mail_user(db):
    return User.objects.create_user(email="cmd@example.com", password="pass12345", name="Cmd")