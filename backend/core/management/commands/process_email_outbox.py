from __future__ import annotations

import logging
import socket
import time
import uuid

from django.core.management.base import BaseCommand, CommandError

from core.outbox.claim import count_eligible, release_worker_lock, try_worker_lock
from core.outbox.health import format_health_report, outbox_health_snapshot
from core.outbox.reporting import format_worker_log_json, format_worker_stdout, worker_result_to_log_dict
from core.outbox.worker import WorkerRunResult, run_worker_pass

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Process pending OutboundEmail rows (short claim transactions; send outside DB txn). "
        "Each claimed row gets a unique claim token in locked_by; --worker-id is for logging only. "
        "Schedule every 1–2 minutes on Render using direct DATABASE_URL (not pooled)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            help="Max rows claimed per batch (positive integer).",
        )
        parser.add_argument(
            "--max-runtime",
            type=int,
            default=0,
            help="Stop after this many seconds (0 = single pass until queue drained or batch empty).",
        )
        parser.add_argument(
            "--worker-id",
            default="",
            help=(
                "Operational label for stdout/logs only (default: hostname + short uuid). "
                "Row ownership uses a per-claim UUID in locked_by, not this value."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Read-only outbox health and eligible count; do not claim or send.",
        )
        parser.add_argument(
            "--no-advisory-lock",
            action="store_true",
            help="Skip pg advisory lock (for tests or overlapping diagnostics only).",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        if batch_size < 1:
            raise CommandError("--batch-size must be a positive integer.")
        max_runtime = options["max_runtime"]
        if max_runtime < 0:
            raise CommandError("--max-runtime must be zero or a positive integer.")

        if options["dry_run"]:
            snapshot = outbox_health_snapshot()
            eligible = count_eligible()
            self.stdout.write(format_health_report(snapshot, eligible=eligible))
            return

        started = time.monotonic()
        lock_held = False
        advisory_lock = "skipped" if options["no_advisory_lock"] else "busy"
        if not options["no_advisory_lock"]:
            lock_held = try_worker_lock()
            if not lock_held:
                duration = time.monotonic() - started
                self.stdout.write(
                    f"advisory_lock=busy duration_seconds={duration:.3f} exit_ok=true exit=0"
                )
                return
            advisory_lock = "acquired"

        worker_id = (options["worker_id"] or "").strip() or f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        operational_error: str | None = None
        result = WorkerRunResult()
        try:
            try:
                result = run_worker_pass(
                    batch_size=batch_size,
                    worker_id=worker_id,
                    max_runtime_seconds=float(max_runtime) if max_runtime else None,
                )
            except Exception as exc:
                operational_error = type(exc).__name__
                logger.exception("outbox_worker operational failure worker_id=%s", worker_id)
                raise CommandError(f"outbox worker operational failure: {operational_error}") from exc
        finally:
            if lock_held:
                release_worker_lock()

        duration = time.monotonic() - started
        log_payload = worker_result_to_log_dict(
            result,
            worker_id=worker_id,
            duration_seconds=duration,
            advisory_lock=advisory_lock,
            operational_error=operational_error,
        )
        logger.info("outbox_worker_run %s", format_worker_log_json(**log_payload))
        self.stdout.write(
            format_worker_stdout(
                result,
                worker_id=worker_id,
                duration_seconds=duration,
                advisory_lock=advisory_lock,
                operational_error=operational_error,
            )
        )