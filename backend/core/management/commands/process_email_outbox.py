from __future__ import annotations

import socket
import uuid

from django.core.management.base import BaseCommand, CommandError

from core.outbox.claim import count_eligible, release_worker_lock, try_worker_lock
from core.outbox.worker import run_worker_pass


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
            help="Report eligible row count only; do not claim or send.",
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
            self.stdout.write(f"eligible={count_eligible()}")
            return

        lock_held = False
        if not options["no_advisory_lock"]:
            lock_held = try_worker_lock()
            if not lock_held:
                self.stdout.write("advisory_lock=busy exit=0")
                return

        worker_id = (options["worker_id"] or "").strip() or f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        try:
            result = run_worker_pass(
                batch_size=batch_size,
                worker_id=worker_id,
                max_runtime_seconds=float(max_runtime) if max_runtime else None,
            )
        finally:
            if lock_held:
                release_worker_lock()

        self.stdout.write(
            "worker_id={worker} claimed={claimed} sent={sent} retry={retry} failed={failed} "
            "cancelled={cancelled} skipped_ownership={skipped}".format(
                worker=worker_id,
                claimed=result.claimed,
                sent=result.sent,
                retry=result.retry,
                failed=result.failed,
                cancelled=result.cancelled,
                skipped=result.skipped_ownership,
            )
        )