"""Daily job structured results and lock visibility (Stage 5.3)."""

from __future__ import annotations

from datetime import date
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import CommandError, call_command
from django.db import connection

from jobs.results import DailyRunResult, format_daily_summary
from jobs import services as job_services

pytestmark = pytest.mark.skipif(connection.vendor != "postgresql", reason="advisory locks require PostgreSQL")


@pytest.mark.django_db
def test_lock_busy_reported_not_none():
    with patch.object(job_services, "_try_advisory_lock", return_value=False):
        result = job_services.run_daily(date(2026, 1, 1))
    assert isinstance(result, DailyRunResult)
    assert result.skipped_due_to_lock is True
    assert result.lock_acquired is False
    assert "lock_acquired=false" in format_daily_summary(result)


@pytest.mark.django_db
def test_run_daily_command_lock_busy_stdout():
    with patch.object(job_services, "_try_advisory_lock", return_value=False):
        out = StringIO()
        call_command("run_daily", "--date=2026-01-01", stdout=out)
    assert "skipped_due_to_lock=true" in out.getvalue()


@pytest.mark.django_db
def test_step_failure_surfaces_in_summary():
    with patch.object(job_services, "_try_advisory_lock", return_value=True):
        with patch.object(job_services, "_advisory_unlock"):
            with patch(
                "jobs.services.billing_services.generate_charges_for_all_plans",
                side_effect=RuntimeError("boom"),
            ):
                with patch(
                    "sharing.services.close_departed_members",
                    return_value=0,
                ):
                    with patch("jobs.services.billing_services.expire_fixed_term_plans", return_value=0):
                        with patch("jobs.services.billing_services.activate_ended_trials", return_value=0):
                            result = job_services.run_daily(date(2026, 3, 1))
    assert result.success is False
    assert result.failed_step == "generate_charges"
    assert result.error_type == "RuntimeError"
    assert "members_closed" in result.steps_completed


@pytest.mark.django_db
def test_run_daily_command_exits_nonzero_on_step_failure():
    with patch.object(job_services, "_try_advisory_lock", return_value=True):
        with patch.object(job_services, "_advisory_unlock"):
            with patch(
                "jobs.services.billing_services.generate_charges_for_all_plans",
                side_effect=RuntimeError("boom"),
            ):
                with patch(
                    "sharing.services.close_departed_members",
                    return_value=0,
                ):
                    with patch("jobs.services.billing_services.expire_fixed_term_plans", return_value=0):
                        with patch("jobs.services.billing_services.activate_ended_trials", return_value=0):
                            with pytest.raises(CommandError, match="generate_charges"):
                                call_command("run_daily", "--date=2026-03-01")