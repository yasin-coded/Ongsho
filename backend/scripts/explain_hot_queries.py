#!/usr/bin/env python
"""Print EXPLAIN (ANALYZE, BUFFERS) node types and timings for hot queries."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from core.dev_db_guard import assert_local_dev_database_or_exit
from django.db import connection

QUERIES = [
    (
        "charge_list_by_subscription",
        """
        SELECT * FROM billing_charge
        WHERE subscription_id = %s
        ORDER BY due_date DESC, id DESC
        LIMIT 25
        """,
        [1],
    ),
    (
        "due_by_member_status",
        """
        SELECT * FROM dues_due
        WHERE member_id = %s AND status = %s
        """,
        [1, "due"],
    ),
    (
        "payment_pending_by_plan",
        """
        SELECT * FROM payments_payment
        WHERE shared_plan_id = %s AND review_status = %s
        """,
        [1, "pending"],
    ),
    (
        "member_active_by_plan",
        """
        SELECT * FROM sharing_member
        WHERE shared_plan_id = %s AND status = %s
        """,
        [1, "active"],
    ),
    (
        "notification_unread",
        """
        SELECT * FROM notifications_notification
        WHERE user_id = %s AND read_at IS NULL
        ORDER BY created_at DESC
        LIMIT 30
        """,
        [1],
    ),
    (
        "audit_by_plan",
        """
        SELECT * FROM audit_auditlog
        WHERE plan_id = %s
        ORDER BY created_at DESC
        LIMIT 50
        """,
        [1],
    ),
]


def _summarize(plan_text: str) -> list[str]:
    lines = []
    for line in plan_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("->") or line.startswith("Index") or "Scan" in line or "time=" in line:
            lines.append(line.split("..")[0][:120])
    return lines[:12]


def main() -> int:
    assert_local_dev_database_or_exit("explain_hot_queries")
    for name, sql, params in QUERIES:
        print(f"\n=== {name} ===")
        with connection.cursor() as cursor:
            cursor.execute(f"EXPLAIN (ANALYZE, BUFFERS) {sql}", params)
            rows = cursor.fetchall()
        text = "\n".join(r[0] for r in rows)
        for line in _summarize(text):
            print(line)
        timing = re.search(r"Execution Time: ([\d.]+) ms", text)
        if timing:
            print(f"timing_ms={timing.group(1)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())