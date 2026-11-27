"""Public email-change verification (POST /api/auth/verify-email-change/)."""

from __future__ import annotations

import time
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core import mail, signing
from rest_framework.test import APIClient

from accounts.cookies import REFRESH_COOKIE_NAME
from accounts.tokens import EMAIL_CHANGE_SALT, make_email_change_token, make_email_verification_token
from audit.models import AuditLog
from core.models.outbound_email import OutboundEmail, OutboundEmailType
from tests.outbox_helpers import flush_outbound_to_mailbox
from tests.test_profile import (
    APP_HEADER,
    STRONG_PASSWORD,
    assert_error_shape,
    client_for,
    extract_email_change_token,
    login_with_cookie,
    make_verified,
    request_email_change,
)

User = get_user_model()

PUBLIC_VERIFY = "/api/auth/verify-email-change/"
REGISTER_VERIFY = "/api/auth/verify-email/"


@pytest.fixture(autouse=True)
def email_change_env(settings):
    settings.FRONTEND_BASE_URL = "http://localhost:5173"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "noreply@example.com"
    settings.REFRESH_COOKIE_SECURE = False
    settings.REFRESH_COOKIE_SAMESITE = "Lax"


def _pending(email="base@example.com", pending="fresh@example.com"):
    user = make_verified(email)
    client = client_for(user)
    mail.outbox.clear()
    request_email_change(client, pending)
    token = extract_email_change_token(mail.outbox[-1].body)
    return user, token, pending


@pytest.mark.django_db
def test_anonymous_success_updates_email():
    user, token, pending = _pending()
    login = login_with_cookie(APIClient(), "base@example.com")
    refresh_before = login.cookies[REFRESH_COOKIE_NAME].value
    response = APIClient().post(PUBLIC_VERIFY, {"token": token}, format="json")
    assert response.status_code == 200
    assert response.json()["email"] == pending
    user.refresh_from_db()
    assert user.email == pending
    assert user.pending_email == ""
    assert user.email_verified is True
    audit = AuditLog.objects.get(user=user, action="email_change.verified")
    assert audit.old_value == {"email": "base@example.com"}
    assert audit.new_value == {"email": pending}
    flush_outbound_to_mailbox()
    assert OutboundEmail.objects.filter(
        user=user,
        email_type__in=(
            OutboundEmailType.EMAIL_CHANGED_NEW,
            OutboundEmailType.EMAIL_CHANGED_PREVIOUS,
        ),
    ).count() == 2
    refreshed = APIClient().post(
        "/api/auth/refresh/",
        format="json",
        HTTP_COOKIE=f"{REFRESH_COOKIE_NAME}={refresh_before}",
        **APP_HEADER,
    )
    assert refreshed.status_code == 401
    assert login_with_cookie(APIClient(), pending).status_code == 200
    assert login_with_cookie(APIClient(), "base@example.com").status_code == 401


@pytest.mark.django_db
def test_registration_token_rejected():
    user = User.objects.create_user(email="r@example.com", password=STRONG_PASSWORD, name="R", email_verified=False)
    token = make_email_verification_token(user)
    response = APIClient().post(PUBLIC_VERIFY, {"token": token}, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_token"


@pytest.mark.django_db
def test_email_change_token_rejected_by_registration_endpoint():
    user, token, _ = _pending()
    response = APIClient().post(REGISTER_VERIFY, {"token": token}, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_token"


@pytest.mark.django_db
def test_garbage_and_expired_tokens():
    assert_error_shape(APIClient().post(PUBLIC_VERIFY, {"token": "garbage"}, format="json"))
    user, _, _ = _pending()
    payload = signing.dumps({"user_id": user.pk, "email": "fresh@example.com"}, salt=EMAIL_CHANGE_SALT)
    future = time.time() + int(timedelta(days=5).total_seconds())
    with patch("django.core.signing.time.time", return_value=future):
        expired = APIClient().post(PUBLIC_VERIFY, {"token": payload}, format="json")
    assert expired.json()["error"]["code"] == "expired_token"


@pytest.mark.django_db
def test_inactive_user_rejected():
    user, token, _ = _pending()
    User.objects.filter(pk=user.pk).update(is_active=False)
    response = APIClient().post(PUBLIC_VERIFY, {"token": token}, format="json")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_inactive"


@pytest.mark.django_db
def test_stale_token_after_newer_request():
    user = make_verified("stale@example.com")
    client = client_for(user)
    mail.outbox.clear()
    request_email_change(client, "first-new@example.com")
    token_first = extract_email_change_token(mail.outbox[-1].body)
    mail.outbox.clear()
    request_email_change(client, "second-new@example.com")
    stale = APIClient().post(PUBLIC_VERIFY, {"token": token_first}, format="json")
    assert stale.json()["error"]["code"] == "email_change_stale"


@pytest.mark.django_db
def test_idempotent_second_verify():
    user, token, pending = _pending()
    anon = APIClient()
    assert anon.post(PUBLIC_VERIFY, {"token": token}, format="json").status_code == 200
    total = AuditLog.objects.filter(user=user, action="email_change.verified").count()
    again = anon.post(PUBLIC_VERIFY, {"token": token}, format="json")
    assert again.status_code == 200
    assert AuditLog.objects.filter(user=user, action="email_change.verified").count() == total
    user.refresh_from_db()
    assert user.email == pending


@pytest.mark.django_db
def test_email_taken_conflict():
    user, token, _ = _pending(pending="taken@example.com")
    make_verified("taken@example.com")
    response = APIClient().post(PUBLIC_VERIFY, {"token": token}, format="json")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


@pytest.mark.django_db
def test_nonexistent_user_id_in_token():
    payload = make_email_change_token(
        type("U", (), {"pk": 999_999, "email": "ghost@example.com"})(),
        "ghost@example.com",
    )
    response = APIClient().post(PUBLIC_VERIFY, {"token": payload}, format="json")
    assert response.json()["error"]["code"] == "invalid_token"


@pytest.mark.django_db
def test_case_insensitive_email_taken():
    user, token, _ = _pending(pending="Taken@Example.com")
    make_verified("taken@example.com")
    response = APIClient().post(PUBLIC_VERIFY, {"token": token}, format="json")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


@pytest.mark.django_db
def test_authenticated_user_cannot_apply_another_users_token():
    user_a = make_verified("a-public@example.com")
    client_b = client_for(make_verified("b-public@example.com"))
    mail.outbox.clear()
    request_email_change(client_b, "b-new-public@example.com")
    token_b = extract_email_change_token(mail.outbox[-1].body)
    response = client_for(user_a).post("/api/me/email/verify/", {"token": token_b}, format="json")
    assert response.json()["error"]["code"] == "invalid_token"