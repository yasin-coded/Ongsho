"""Structured results for daily job runs (no PII)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class DailyRunResult:
    run_date: date
    lock_acquired: bool
    skipped_due_to_lock: bool = False
    success: bool = True
    duration_seconds: float = 0.0
    counts: dict[str, Any] = field(default_factory=dict)
    steps_completed: list[str] = field(default_factory=list)
    failed_step: str | None = None
    error_type: str | None = None

    def to_log_dict(self) -> dict[str, Any]:
        return {
            "run_date": self.run_date.isoformat(),
            "lock_acquired": self.lock_acquired,
            "skipped_due_to_lock": self.skipped_due_to_lock,
            "success": self.success,
            "duration_seconds": round(self.duration_seconds, 3),
            "failed_step": self.failed_step,
            "error_type": self.error_type,
            "steps_completed": list(self.steps_completed),
            "counts": dict(self.counts),
        }


def format_daily_summary(result: DailyRunResult) -> str:
    if result.skipped_due_to_lock:
        return (
            f"run_date={result.run_date.isoformat()} lock_acquired=false "
            f"skipped_due_to_lock=true duration_seconds={result.duration_seconds:.3f} exit=0"
        )
    parts = [
        f"run_date={result.run_date.isoformat()}",
        f"lock_acquired=true",
        f"success={str(result.success).lower()}",
        f"duration_seconds={result.duration_seconds:.3f}",
    ]
    if result.failed_step:
        parts.append(f"failed_step={result.failed_step}")
    if result.error_type:
        parts.append(f"error_type={result.error_type}")
    for key, value in sorted(result.counts.items()):
        parts.append(f"{key}={value}")
    if result.steps_completed:
        parts.append("steps=" + ",".join(result.steps_completed))
    return " ".join(parts)