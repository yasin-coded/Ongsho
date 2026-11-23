from __future__ import annotations

import logging
from unittest import mock

import pytest
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

READY_URL = "/api/health/ready/"


@override_settings(SESSION_ENGINE="django.contrib.sessions.backends.cache")
def test_health_get_no_auth_no_db(caplog):
    caplog.set_level(logging.DEBUG, logger="ongsho.request")
    client = APIClient()
    with CaptureQueriesContext(connection) as ctx:
        response = client.get("/api/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response["Cache-Control"] == "no-store"
    assert len(ctx.captured_queries) == 0
    info_logs = [r for r in caplog.records if r.levelno == logging.INFO and "route=health" in r.getMessage()]
    assert not info_logs
    debug_logs = [r for r in caplog.records if r.levelno == logging.DEBUG and "route=health" in r.getMessage()]
    assert debug_logs


def test_health_head():
    client = APIClient()
    response = client.head("/api/health/")
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_health_ready_get_success():
    client = APIClient()
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(READY_URL)
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    assert response["Cache-Control"] == "no-store"
    assert any("SELECT 1" in q["sql"] for q in ctx.captured_queries)


@pytest.mark.django_db
def test_health_ready_head_success():
    client = APIClient()
    response = client.head(READY_URL)
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"


def test_health_ready_database_unavailable():
    client = APIClient()
    secret = "postgresql://user:sekret@host/db"
    with mock.patch.object(
        connection,
        "cursor",
        side_effect=RuntimeError(f"connection failed {secret}"),
    ):
        response = client.get(READY_URL)
    assert response.status_code == 503
    body = response.json()
    assert body == {"status": "unavailable", "database": "unavailable"}
    assert secret not in response.content.decode()