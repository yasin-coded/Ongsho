"""Operator-safe stdout and log formatting for outbox worker runs."""

from __future__ import annotations

import json
from typing import Any

from core.outbox.worker import WorkerRunResult


def worker_result_to_log_dict(
    result: WorkerRunResult,
    *,
    worker_id: str,
    duration_seconds: float,
    advisory_lock: str,
    operational_error: str | None = None,
) -> dict[str, Any]:
    return {
        "worker_id": worker_id,
        "advisory_lock": advisory_lock,
        "duration_seconds": round(duration_seconds, 3),
        "claimed": result.claimed,
        "sent": result.sent,
        "retry": result.retry,
        "failed": result.failed,
        "cancelled": result.cancelled,
        "skipped_ownership": result.skipped_ownership,
        "eligible_remaining": result.eligible_remaining,
        "operational_error": operational_error,
        "exit_ok": operational_error is None,
    }


def format_worker_stdout(
    result: WorkerRunResult,
    *,
    worker_id: str,
    duration_seconds: float,
    advisory_lock: str,
    operational_error: str | None = None,
) -> str:
    lines = [
        f"worker_id={worker_id}",
        f"advisory_lock={advisory_lock}",
        f"duration_seconds={duration_seconds:.3f}",
        f"claimed={result.claimed}",
        f"sent={result.sent}",
        f"retry={result.retry}",
        f"failed={result.failed}",
        f"cancelled={result.cancelled}",
        f"skipped_ownership={result.skipped_ownership}",
        f"eligible_remaining={result.eligible_remaining}",
        f"exit_ok={str(operational_error is None).lower()}",
    ]
    if operational_error:
        lines.append(f"operational_error={operational_error}")
    return "\n".join(lines)


def format_worker_log_json(**fields: Any) -> str:
    safe = {k: v for k, v in fields.items() if v is not None}
    return json.dumps(safe, sort_keys=True)