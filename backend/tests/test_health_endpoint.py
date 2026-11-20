from __future__ import annotations

import logging

import pytest
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient


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