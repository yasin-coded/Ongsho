"""Origin allow-list on cookie auth endpoints (hardening Part 3)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from tests.test_auth import login_user

User = get_user_model()
GOOD_ORIGIN = "http://localhost:5173"
BAD_ORIGIN = "http://evil.example"
APP_HEADER = {"HTTP_X_REQUESTED_WITH": "Ongsho"}


@pytest.fixture
def verified_user(db):
    return User.objects.create_user(
        email="origin@example.com", password="HorseBatteryStaple99", name="O", email_verified=True
    )


@pytest.mark.django_db
def test_refresh_rejects_bad_origin(verified_user, settings):
    settings.CORS_ALLOWED_ORIGINS = [GOOD_ORIGIN]
    client = APIClient()
    login = login_user(client, "origin@example.com")
    assert login.status_code == 200
    client.cookies.update(login.cookies)
    response = client.post(
        "/api/auth/refresh/",
        {},
        format="json",
        HTTP_ORIGIN=BAD_ORIGIN,
        **APP_HEADER,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "bad_origin"


@pytest.mark.django_db
def test_refresh_accepts_allowed_origin(verified_user, settings):
    settings.CORS_ALLOWED_ORIGINS = [GOOD_ORIGIN]
    client = APIClient()
    login = login_user(client, "origin@example.com")
    assert login.status_code == 200
    client.cookies.update(login.cookies)
    response = client.post(
        "/api/auth/refresh/",
        {},
        format="json",
        HTTP_ORIGIN=GOOD_ORIGIN,
        **APP_HEADER,
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_refresh_without_origin_requires_app_header(verified_user):
    client = APIClient()
    login = login_user(client, "origin@example.com")
    client.cookies.update(login.cookies)
    missing = client.post("/api/auth/refresh/", {}, format="json")
    assert missing.status_code == 403
    assert missing.json()["error"]["code"] == "missing_app_header"

    ok = client.post("/api/auth/refresh/", {}, format="json", **APP_HEADER)
    assert ok.status_code == 200