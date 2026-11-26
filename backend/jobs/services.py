from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from datetime import date
from typing import Any

from django.db import connection

from billing import services as billing_services
from jobs.results import DailyRunResult

logger = logging.getLogger(__name__)

_DAILY_LOCK_ID = 86420101


def _try_advisory_lock() -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [_DAILY_LOCK_ID])
        return bool(cursor.fetchone()[0])


def _advisory_unlock() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_unlock(%s)", [_DAILY_LOCK_ID])


def run_daily(today: date) -> DailyRunResult:
    """Run billing maintenance for ``today``."""
    started = time.monotonic()

    if not _try_advisory_lock():
        duration = time.monotonic() - started
        result = DailyRunResult(
            run_date=today,
            lock_acquired=False,
            skipped_due_to_lock=True,
            success=True,
            duration_seconds=duration,
        )
        logger.info("run_daily skipped lock_busy run_date=%s duration_seconds=%.3f", today, duration)
        return result

    steps_completed: list[str] = []
    counts: dict[str, Any] = {}
    try:
        from dues import services as dues_services
        from notifications.reminders import send_reminders
        from sharing import services as sharing_services

        steps: list[tuple[str, Callable[[], Any]]] = [
            ("members_closed", lambda: sharing_services.close_departed_members(today)),
            ("expired", lambda: billing_services.expire_fixed_term_plans(today)),
            ("trials_activated", lambda: billing_services.activate_ended_trials(today)),
            (
                "generate_charges",
                lambda: billing_services.generate_charges_for_all_plans(today),
            ),
            ("lock_charges", lambda: billing_services.lock_due_charges(today)),
            ("ensure_dues", lambda: dues_services.ensure_dues(today)),
            ("send_reminders", lambda: send_reminders(today)),
        ]

        for step_name, step_fn in steps:
            try:
                value = step_fn()
            except Exception as exc:
                logger.exception("run_daily step=%s failed run_date=%s", step_name, today)
                duration = time.monotonic() - started
                return DailyRunResult(
                    run_date=today,
                    lock_acquired=True,
                    success=False,
                    duration_seconds=duration,
                    counts=counts,
                    steps_completed=steps_completed,
                    failed_step=step_name,
                    error_type=type(exc).__name__,
                )
            if step_name == "generate_charges":
                counts["plans_processed"] = value["plans"]
                counts["charges_created"] = value["created"]
                counts["charge_errors"] = value["errors"]
            elif step_name == "send_reminders":
                counts.update(value)
            else:
                counts[step_name] = value
            steps_completed.append(step_name)

        duration = time.monotonic() - started
        result = DailyRunResult(
            run_date=today,
            lock_acquired=True,
            success=True,
            duration_seconds=duration,
            counts=counts,
            steps_completed=steps_completed,
        )
        logger.info("run_daily %s", json.dumps(result.to_log_dict(), sort_keys=True))
        return result
    finally:
        _advisory_unlock()