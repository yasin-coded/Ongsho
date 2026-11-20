"""Query-count budgets for hot list endpoints (Part C)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test.utils import CaptureQueriesContext
from django.db import connection

from catalog.models import Category, ServiceName
from core.choices import PaymentMethod
from core.dates import today_dhaka
from plans.models import CycleUnit, PlanMode, RenewalType, Subscription, SubscriptionStatus
from tests.test_subscriptions import WORLD_PASS, client_for, plan_payload

User = get_user_model()


@pytest.fixture
def perf_owner(db):
    from tests.helpers import ensure_catalog_presets

    ensure_catalog_presets()
    owner = User.objects.create_user(
        email="perfowner@example.com",
        password=WORLD_PASS,
        name="Perf Owner",
        email_verified=True,
    )
    client = client_for(owner)
    for i in range(30):
        client.post(
            "/api/subscriptions/",
            {**plan_payload(plan_name=f"Perf {i}"), "seats": 8},
            format="json",
        )
    return owner


def _assert_max_queries(owner, method: str, path: str, budget: int, **kwargs):
    client = client_for(owner)
    with CaptureQueriesContext(connection) as ctx:
        response = getattr(client, method.lower())(path, **kwargs)
    assert response.status_code in (200, 201), response.content
    assert len(ctx) <= budget, f"{path} used {len(ctx)} queries (budget {budget})"


@pytest.mark.django_db
def test_budget_plans_list(perf_owner):
    _assert_max_queries(perf_owner, "GET", "/api/subscriptions/", 15)


@pytest.mark.django_db
def test_budget_dashboard_summary(perf_owner):
    _assert_max_queries(perf_owner, "GET", "/api/dashboard/summary/", 25)


@pytest.mark.django_db
def test_budget_dashboard_forecast(perf_owner):
    _assert_max_queries(perf_owner, "GET", "/api/dashboard/forecast/", 15)


@pytest.mark.django_db
def test_budget_notifications_list(perf_owner):
    _assert_max_queries(perf_owner, "GET", "/api/notifications/", 20)


@pytest.mark.django_db
def test_budget_calendar(perf_owner):
    _assert_max_queries(perf_owner, "GET", "/api/calendar/", 15)


@pytest.mark.django_db
def test_budget_dues_list(perf_owner):
    _assert_max_queries(perf_owner, "GET", "/api/dues/", 10)


@pytest.mark.django_db
def test_budget_nav_counts(perf_owner):
    _assert_max_queries(perf_owner, "GET", "/api/me/nav-counts/", 4)


@pytest.mark.django_db
def test_budget_charges_list(perf_owner):
    sub = Subscription.objects.filter(owner=perf_owner).first()
    _assert_max_queries(perf_owner, "GET", f"/api/charges/?plan={sub.pk}", 12)


@pytest.mark.django_db
def test_budget_members_list(perf_owner):
    sub = Subscription.objects.filter(owner=perf_owner).first()
    _assert_max_queries(perf_owner, "GET", f"/api/shared-plans/{sub.pk}/members/", 12)


@pytest.mark.django_db
def test_budget_review(perf_owner):
    sub = Subscription.objects.filter(owner=perf_owner).first()
    _assert_max_queries(perf_owner, "GET", f"/api/shared-plans/{sub.pk}/review/", 20)


@pytest.mark.django_db
def test_budget_ledger(perf_owner):
    sub = Subscription.objects.filter(owner=perf_owner).first()
    _assert_max_queries(perf_owner, "GET", f"/api/shared-plans/{sub.pk}/ledger/", 12)


@pytest.mark.django_db
def test_slow_request_warning_logged(settings, caplog):
    import logging

    settings.SLOW_REQUEST_MS = 0
    caplog.set_level(logging.WARNING, logger="ongsho.request")
    owner = User.objects.create_user(
        email="slow@example.com",
        password=WORLD_PASS,
        name="Slow",
        email_verified=True,
    )
    client = client_for(owner)
    client.get("/api/me/")
    assert any("slow_request" in r.message for r in caplog.records)