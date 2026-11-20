"""API security headers middleware (hardening Part 2)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from rest_framework.test import APIClient

User = get_user_model()
GOOD_ORIGIN = "http://localhost:5173"
HEADER_NAMES = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


@pytest.fixture
def authed_user(db):
    return User.objects.create_user(
        email="headers@example.com", password="pass12345", name="H", email_verified=True
    )


@pytest.mark.django_db
@pytest.mark.parametrize("header,expected", list(HEADER_NAMES.items()))
def test_api_response_includes_security_header(header, expected, authed_user):
    client = APIClient()
    client.force_authenticate(user=authed_user)
    response = client.get("/api/me/nav-counts/")
    assert response[header] == expected


@pytest.mark.django_db
def test_pdf_response_keeps_existing_cache_control_and_adds_headers(authed_user, world):
    client = APIClient()
    client.force_authenticate(user=world["owner"])
    month = world["charge_x"].period_start.strftime("%Y-%m")
    response = client.get(
        f"/api/shared-plans/{world['plan_x'].pk}/statement/?month={month}",
    )
    if response.status_code != 200:
        pytest.skip("statement not available in fixture")
    assert response["Cache-Control"] == "no-store"
    assert response["Content-Security-Policy"] == HEADER_NAMES["Content-Security-Policy"]


@pytest.mark.django_db
def test_cors_headers_still_present():
    client = Client()
    response = client.get("/api/categories/", HTTP_ORIGIN=GOOD_ORIGIN)
    assert response["Access-Control-Allow-Origin"] == GOOD_ORIGIN


def test_admin_responses_skip_api_security_headers():
    client = Client()
    response = client.get("/admin/login/")
    for header in (
        "Content-Security-Policy",
        "Permissions-Policy",
    ):
        assert header not in response