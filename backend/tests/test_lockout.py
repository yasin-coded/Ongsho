import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from accounts.services import verify_current_password
from core.exceptions import Locked, ValidationFailed
from tests.test_auth import STRONG_PASSWORD, register_user, verify_from_outbox
from tests.test_subscriptions import WORLD_PASS, client_for, plan_payload

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient()


def _login_fail(client, email, ip):
    return client.post(
        "/api/auth/login/",
        {"email": email, "password": "not-the-password"},
        format="json",
        REMOTE_ADDR=ip,
    )


def _assert_locked(response):
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "locked"
    assert response.headers.get("Retry-After") or response.get("Retry-After")


def test_login_pair_lockout_same_response_unknown_email(api_client):
    email = "nobody@example.com"
    for _ in range(5):
        assert _login_fail(api_client, email, "2.2.2.2").status_code == 401
    locked_unknown = _login_fail(api_client, email, "2.2.2.2")
    _assert_locked(locked_unknown)

    user = User.objects.create_user(
        email="real@example.com", password=STRONG_PASSWORD, name="Real", email_verified=True
    )
    for _ in range(5):
        assert _login_fail(api_client, user.email, "3.3.3.3").status_code == 401
    locked_known = api_client.post(
        "/api/auth/login/",
        {"email": user.email, "password": STRONG_PASSWORD},
        format="json",
        REMOTE_ADDR="3.3.3.3",
    )
    _assert_locked(locked_known)
    assert locked_unknown.json()["error"]["message"] == locked_known.json()["error"]["message"]


def test_login_success_clears_pair_counter(api_client):
    email = "clear-pair@example.com"
    register_user(api_client, email=email)
    verify_from_outbox(api_client)
    for _ in range(4):
        _login_fail(api_client, email, "4.4.4.4")
    ok = api_client.post(
        "/api/auth/login/",
        {"email": email, "password": STRONG_PASSWORD},
        format="json",
        REMOTE_ADDR="4.4.4.4",
    )
    assert ok.status_code == 200
    for _ in range(4):
        _login_fail(api_client, email, "4.4.4.4")
    again = api_client.post(
        "/api/auth/login/",
        {"email": email, "password": STRONG_PASSWORD},
        format="json",
        REMOTE_ADDR="4.4.4.4",
    )
    assert again.status_code == 200


def test_login_email_lockout_across_ips(api_client, settings):
    settings.THROTTLE_RATES = {**settings.THROTTLE_RATES, "login_email": "100/15m", "login_ip": "100/m"}
    email = "wide-lock@example.com"
    for i in range(20):
        assert _login_fail(api_client, email, f"10.1.0.{i}").status_code == 401
    locked = _login_fail(api_client, email, "10.1.0.99")
    _assert_locked(locked)


def test_password_confirm_lockout_shared_across_actions(db):
    user = User.objects.create_user(
        email="pwlock@example.com", password=WORLD_PASS, name="Pw", email_verified=True
    )
    for _ in range(5):
        with pytest.raises(ValidationFailed):
            verify_current_password(user, "bad-password")

    with pytest.raises(Locked):
        verify_current_password(user, WORLD_PASS)

    owner_client = client_for(user)
    r = owner_client.post(
        "/api/subscriptions/",
        {**plan_payload()},
        format="json",
    )
    assert r.status_code == 201
    plan_id = r.json()["id"]

    delete_locked = owner_client.delete(
        f"/api/subscriptions/{plan_id}/",
        {"password": WORLD_PASS},
        format="json",
    )
    _assert_locked(delete_locked)