from __future__ import annotations

import logging

from django.db import connection

from billing import services as billing_services

logger = logging.getLogger(__name__)

_DAILY_LOCK_ID = 86420101


def _try_advisory_lock() -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [_DAILY_LOCK_ID])
        return bool(cursor.fetchone()[0])


def _advisory_unlock() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_unlock(%s)", [_DAILY_LOCK_ID])


def run_daily(today) -> dict[str, int] | None:
    """Run billing maintenance for ``today``. Returns None when lock not acquired."""
    if not _try_advisory_lock():
        return None
    try:
        from sharing import services as sharing_services

        departed = sharing_services.close_departed_members(today)
        expired = billing_services.expire_fixed_term_plans(today)
        trials = billing_services.activate_ended_trials(today)
        generated = billing_services.generate_charges_for_all_plans(today)
        locked = billing_services.lock_due_charges(today)
        from dues import services as dues_services

        dues_ensured = dues_services.ensure_dues(today)
        # TODO(notifications): enqueue renewal and due reminders once reminder jobs exist.
        return {
            "members_closed": departed,
            "expired": expired,
            "trials_activated": trials,
            "plans_processed": generated["plans"],
            "charges_created": generated["created"],
            "charge_errors": generated["errors"],
            "charges_locked": locked,
            "dues_ensured": dues_ensured,
        }
    finally:
        _advisory_unlock()
