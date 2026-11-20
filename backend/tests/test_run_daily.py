from datetime import date
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.db import connection

from billing.models import Charge
from billing.services import generate_missing_charges
from jobs.services import _DAILY_LOCK_ID
from plans.models import CycleUnit, PlanMode, RenewalType, Subscription, SubscriptionStatus
from tests.test_billing_generator import _plan

pytestmark = pytest.mark.skipif(connection.vendor != "postgresql", reason="advisory locks require PostgreSQL")


@pytest.fixture
def owner(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        email="daily@example.com", password="pass12345", name="Daily", email_verified=True
    )


@pytest.mark.django_db
def test_run_daily_steps_in_order(owner):
    calls = []

    def recorder(name, today):
        calls.append(name)

    def _gen(_today):
        recorder("generate", _today)
        return {"plans": 0, "created": 0, "errors": 0}

    with (
        patch("sharing.services.close_departed_members", side_effect=lambda t: recorder("depart", t) or 0),
        patch("jobs.services.billing_services.expire_fixed_term_plans", side_effect=lambda t: recorder("expire", t) or 0),
        patch("jobs.services.billing_services.activate_ended_trials", side_effect=lambda t: recorder("trial", t) or 0),
        patch("jobs.services.billing_services.generate_charges_for_all_plans", side_effect=_gen),
        patch("jobs.services.billing_services.lock_due_charges", side_effect=lambda t: recorder("lock", t) or 0),
        patch("dues.services.ensure_dues", side_effect=lambda t: recorder("dues", t) or 0),
        patch(
            "notifications.reminders.send_reminders",
            side_effect=lambda t: recorder("reminders", t)
            or {"owner_reminders": 0, "member_reminders": 0, "emails_sent": 0, "emails_failed": 0},
        ),
    ):
        from jobs import services as job_services

        job_services.run_daily(date(2026, 1, 15))
    assert calls == ["depart", "expire", "trial", "generate", "lock", "dues", "reminders"]


@pytest.mark.django_db
def test_run_daily_idempotent_second_run(owner):
    sub = _plan(owner, billing_from=date(2026, 1, 5))
    out1 = StringIO()
    out2 = StringIO()
    call_command("run_daily", "--date=2026-01-26", stdout=out1)
    before = Charge.objects.filter(subscription=sub).count()
    call_command("run_daily", "--date=2026-01-26", stdout=out2)
    assert Charge.objects.filter(subscription=sub).count() == before
    assert "charges_created=0" in out2.getvalue() or "charges_created=" in out2.getvalue()


@pytest.mark.django_db
def test_run_daily_respects_custom_date(owner):
    sub = _plan(
        owner,
        renewal_type=RenewalType.FIXED_TERM,
        end_date=date(2026, 12, 5),
        start_date=date(2026, 9, 5),
        billing_from=date(2026, 9, 5),
        anchor_day=5,
        status=SubscriptionStatus.ACTIVE,
    )
    call_command("run_daily", "--date=2026-12-05")
    sub.refresh_from_db()
    assert sub.status == SubscriptionStatus.EXPIRED


@pytest.mark.django_db
def test_held_advisory_lock_exits_quietly():
    from jobs import services as job_services

    with patch.object(job_services, "_try_advisory_lock", return_value=False):
        assert job_services.run_daily(date(2026, 1, 1)) is None


@pytest.mark.django_db
def test_trial_activation_on_run_daily(owner):
    sub = _plan(
        owner,
        trial_end_date=date(2026, 1, 20),
        status=SubscriptionStatus.TRIAL,
        billing_from=date(2026, 1, 5),
    )
    call_command("run_daily", "--date=2026-01-20")
    sub.refresh_from_db()
    assert sub.status == SubscriptionStatus.ACTIVE
