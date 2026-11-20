import time
from unittest.mock import patch

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from tests.test_auth import STRONG_PASSWORD, register_user, verify_from_outbox

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _throttle_auth_env(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.FRONTEND_BASE_URL = "http://localhost:5173"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def tight_throttles(settings):
    settings.THROTTLE_RATES = {
        **settings.THROTTLE_RATES,
        "login_ip": "2/m",
        "login_email": "5/15m",
        "register_ip": "2/h",
    }


def _assert_throttled(response):
    assert response.status_code == 429
    body = response.json()
    assert body["error"]["code"] == "throttled"
    assert response.headers.get("Retry-After") or response.get("Retry-After")


@pytest.mark.usefixtures("tight_throttles")
def test_login_ip_throttle_returns_envelope(client):
    email = "throttle-ip@example.com"
    register_user(client, email=email)
    verify_from_outbox(client)
    for _ in range(2):
        ok = client.post(
            "/api/auth/login/",
            {"email": email, "password": STRONG_PASSWORD},
            format="json",
            REMOTE_ADDR="1.2.3.4",
        )
        assert ok.status_code == 200
    blocked = client.post(
        "/api/auth/login/",
        {"email": email, "password": STRONG_PASSWORD},
        format="json",
        REMOTE_ADDR="1.2.3.4",
    )
    _assert_throttled(blocked)


@pytest.mark.usefixtures("tight_throttles")
def test_login_email_throttle_independent_of_ip(client, settings):
    settings.THROTTLE_RATES = {**settings.THROTTLE_RATES, "login_email": "3/15m", "login_ip": "100/m"}
    email = "throttle-email@example.com"
    register_user(client, email=email)
    verify_from_outbox(client)
    for i in range(3):
        client.post(
            "/api/auth/login/",
            {"email": email, "password": "wrong-password-123"},
            format="json",
            REMOTE_ADDR=f"10.0.0.{i}",
        )
    throttled = client.post(
        "/api/auth/login/",
        {"email": email, "password": STRONG_PASSWORD},
        format="json",
        REMOTE_ADDR="9.9.9.9",
    )
    _assert_throttled(throttled)


@pytest.mark.usefixtures("tight_throttles")
def test_register_ip_throttle(client):
    for i in range(2):
        r = client.post(
            "/api/auth/register/",
            {"email": f"reg{i}@example.com", "password": STRONG_PASSWORD, "name": "User"},
            format="json",
            REMOTE_ADDR="8.8.8.8",
        )
        assert r.status_code == 201
    blocked = client.post(
        "/api/auth/register/",
        {"email": "reg3@example.com", "password": STRONG_PASSWORD, "name": "User"},
        format="json",
        REMOTE_ADDR="8.8.8.8",
    )
    _assert_throttled(blocked)


def test_x_forwarded_for_ignored_when_num_proxies_zero(client, settings):
    settings.THROTTLE_RATES = {**settings.THROTTLE_RATES, "register_ip": "1/h"}
    settings.NUM_PROXIES = 0
    r1 = client.post(
        "/api/auth/register/",
        {"email": "xff-a@example.com", "password": STRONG_PASSWORD, "name": "User"},
        format="json",
        REMOTE_ADDR="1.1.1.1",
    )
    assert r1.status_code == 201
    r2 = client.post(
        "/api/auth/register/",
        {"email": "xff-b@example.com", "password": STRONG_PASSWORD, "name": "User"},
        format="json",
        REMOTE_ADDR="1.1.1.1",
        HTTP_X_FORWARDED_FOR="9.9.9.9, 1.1.1.1",
    )
    _assert_throttled(r2)


@pytest.mark.usefixtures("tight_throttles")
def test_throttle_recovers_after_window(client):
    email = "recover@example.com"
    register_user(client, email=email)
    verify_from_outbox(client)
    for _ in range(2):
        client.post(
            "/api/auth/login/",
            {"email": email, "password": STRONG_PASSWORD},
            format="json",
            REMOTE_ADDR="5.5.5.5",
        )
    blocked = client.post(
        "/api/auth/login/",
        {"email": email, "password": STRONG_PASSWORD},
        format="json",
        REMOTE_ADDR="5.5.5.5",
    )
    _assert_throttled(blocked)

    future = time.time() + 61
    with patch("rest_framework.throttling.time.time", return_value=future):
        cache.clear()
        ok = client.post(
            "/api/auth/login/",
            {"email": email, "password": STRONG_PASSWORD},
            format="json",
            REMOTE_ADDR="5.5.5.5",
        )
        assert ok.status_code == 200