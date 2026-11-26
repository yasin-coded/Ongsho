"""CI workflow presence and safety gates (structure only — not a live GitHub run)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "rel_path,needles",
    [
        (
            ".github/workflows/ci.yml",
            (
                "postgres:",
                "python -m pytest",
                "makemigrations --check",
                "scan_secrets.py",
                "frontend/webapp",
                "npm ci",
            ),
        ),
        (
            ".github/workflows/run-daily-job.yml",
            (
                "RUN_DAILY_JOB_ENABLED",
                "confirm_live_processing",
                "python manage.py run_daily",
            ),
        ),
    ],
)
def test_workflow_files_define_required_gates(rel_path, needles):
    text = (REPO / rel_path).read_text(encoding="utf-8")
    for needle in needles:
        assert needle in text, f"missing {needle!r} in {rel_path}"


def test_ci_does_not_reference_production_secrets_in_plain_env():
    ci = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "${{ secrets." not in ci
    assert "BREVO_API_KEY" not in ci