import re
import time
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail, signing
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from accounts.constants import DEFAULT_AVATAR_ID
from accounts.tokens import EMAIL_VERIFY_SALT, make_email_verification_token
from core.mail_enqueue import OutboxEnqueueError
from tests.outbox_helpers import flush_outbound_to_mailbox, run_pending_on_commit_hooks

User = get_user_model()

APP_HEADER = {"HTTP_X_REQUESTED_WITH": "Ongsho"}
STRONG_PASSWORD = "HorseBatteryStaple99"
WEAK_PASSWORD = "123"


@pytest.fixture(autouse=True)
def auth_env(settings):
    settings.FRONTEND_BASE_URL = "http://localhost:5173"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "noreply@example.com"
    settings.REFRESH_COOKIE_SECURE = False
    settings.REFRESH_COOKIE_SAMESITE = "Lax"


@pytest.fixture
def api_client():
    return APIClient()


def assert_error_shape(response):
    assert response.status_code >= 400
    data = response.json()
    assert "error" in data
    err = data["error"]
    assert set(err.keys()) == {"code", "message", "fields"}
    assert isinstance(err["fields"], dict)


def register_user(client, email="new@example.com", password=STRONG_PASSWORD, name="New User"):
    return client.post(
        "/api/auth/register/",
        {"email": email, "password": password, "name": name},
        format="json",
    )


def login_user(client, email, password=STRONG_PASSWORD):
    return client.post("/api/auth/login/", {"email": email, "password": password}, format="json")


def verify_from_outbox(client):
    flush_outbound_to_mailbox()
    assert len(mail.outbox) >= 1
    body = mail.outbox[-1].body
    match = re.search(r"token=([^\s]+)", body)
    assert match
    return client.post("/api/auth/verify-email/", {"token": match.group(1)}, format="json")


@pytest.mark.django_db
class TestRegister:
    def test_success(self, api_client):
        mail.outbox.clear()
        response = register_user(api_client)
        assert response.status_code == 201
        assert "refresh" not in response.json()
        assert "access" not in response.json()
        user = User.objects.get(email="new@example.com")
        assert user.email_verified is False
        assert user.check_password(STRONG_PASSWORD)
        assert user.email == "new@example.com"
        assert user.avatar_id == DEFAULT_AVATAR_ID
        flush_outbound_to_mailbox()
        assert len(mail.outbox) == 1
        assert settings.FRONTEND_BASE_URL in mail.outbox[0].body
        verify_from_outbox(api_client)
        user.refresh_from_db()
        assert user.email_verified

    def test_duplicate_email_case_insensitive(self, api_client):
        register_user(api_client, email="Dup@Example.com")
        response = register_user(api_client, email="dup@example.com", name="Other")
        assert_error_shape(response)
        assert response.status_code == 400
        assert response.json()["error"]["fields"]["email"]

    def test_weak_password(self, api_client):
        response = register_user(api_client, password=WEAK_PASSWORD)
        assert_error_shape(response)
        assert response.status_code == 400

    def test_invalid_email(self, api_client):
        response = register_user(api_client, email="not-an-email")
        assert_error_shape(response)

    def test_missing_fields(self, api_client):
        response = api_client.post("/api/auth/register/", {}, format="json")
        assert_error_shape(response)
        assert response.json()["error"]["fields"]


@pytest.mark.django_db
class TestVerifyEmail:
    def test_success_and_twice(self, api_client):
        register_user(api_client)
        mail.outbox.clear()
        user = User.objects.get(email="new@example.com")
        token = make_email_verification_token(user)
        r1 = api_client.post("/api/auth/verify-email/", {"token": token}, format="json")
        assert r1.status_code == 200
        user.refresh_from_db()
        assert user.email_verified
        r2 = api_client.post("/api/auth/verify-email/", {"token": token}, format="json")
        assert r2.status_code == 200

    def test_garbage_token(self, api_client):
        response = api_client.post("/api/auth/verify-email/", {"token": "garbage"}, format="json")
        assert_error_shape(response)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_token"

    def test_expired_token(self, api_client):
        user = User.objects.create_user(email="exp@example.com", password=STRONG_PASSWORD, name="Exp")
        payload = signing.dumps({"user_id": user.pk, "email": user.email}, salt=EMAIL_VERIFY_SALT)
        future = time.time() + int(timedelta(days=5).total_seconds())
        with patch("django.core.signing.time.time", return_value=future):
            response = api_client.post("/api/auth/verify-email/", {"token": payload}, format="json")
        assert response.json()["error"]["code"] == "invalid_token"

    def test_email_changed(self, api_client):
        user = User.objects.create_user(email="old@example.com", password=STRONG_PASSWORD, name="X")
        token = make_email_verification_token(user)
        user.email = "newaddr@example.com"
        user.save(update_fields=["email"])
        response = api_client.post("/api/auth/verify-email/", {"token": token}, format="json")
        assert response.json()["error"]["code"] == "invalid_token"


@pytest.mark.django_db
class TestLogin:
    def test_unverified_forbidden(self, api_client):
        User.objects.create_user(email="unv@example.com", password=STRONG_PASSWORD, name="U", email_verified=False)
        response = login_user(api_client, "unv@example.com")
        assert_error_shape(response)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "email_not_verified"

    def test_wrong_and_unknown_same_body(self, api_client):
        User.objects.create_user(email="good@example.com", password=STRONG_PASSWORD, name="G", email_verified=True)
        wrong = login_user(api_client, "good@example.com", "wrong-pass-xyz")
        unknown = login_user(api_client, "nobody@example.com")
        assert wrong.status_code == 401
        assert unknown.status_code == 401
        assert wrong.json() == unknown.json()
        assert wrong.json()["error"]["code"] == "invalid_credentials"

    def test_inactive_same_as_unknown(self, api_client):
        User.objects.create_user(
            email="inactive@example.com", password=STRONG_PASSWORD, name="I", email_verified=True, is_active=False
        )
        inactive = login_user(api_client, "inactive@example.com")
        unknown = login_user(api_client, "ghost@example.com")
        assert inactive.json() == unknown.json()

    def test_success_cookie_and_access(self, api_client):
        user = User.objects.create_user(email="ok@example.com", password=STRONG_PASSWORD, name="Ok", email_verified=True)
        response = login_user(api_client, "ok@example.com")
        assert response.status_code == 200
        body = response.json()
        assert "access" in body
        assert "refresh" not in body
        assert body["user"]["id"] == user.pk
        cookie = response.cookies.get("refresh_token")
        assert cookie is not None
        assert cookie["httponly"]
        assert cookie["path"] == "/api/auth/"


@pytest.mark.django_db
class TestAccessJWTInactive:
    def test_inactive_user_access_token_rejected(self, api_client):
        from rest_framework_simplejwt.tokens import RefreshToken

        user = User.objects.create_user(
            email="jwt-inactive@example.com",
            password=STRONG_PASSWORD,
            name="Off",
            email_verified=True,
            is_active=False,
        )
        access = str(RefreshToken.for_user(user).access_token)
        response = api_client.get(
            "/api/me/",
            HTTP_AUTHORIZATION=f"Bearer {access}",
            **APP_HEADER,
        )
        assert response.status_code == 401
        assert_error_shape(response)
        assert response.json()["error"]["code"] == "user_inactive"

    def test_active_user_access_token_accepted(self, api_client):
        user = User.objects.create_user(
            email="jwt-active@example.com",
            password=STRONG_PASSWORD,
            name="On",
            email_verified=True,
        )
        from rest_framework_simplejwt.tokens import RefreshToken

        access = str(RefreshToken.for_user(user).access_token)
        response = api_client.get(
            "/api/me/",
            HTTP_AUTHORIZATION=f"Bearer {access}",
            **APP_HEADER,
        )
        assert response.status_code == 200
        assert response.json()["email"] == user.email


@pytest.mark.django_db
class TestRefreshLogout:
    def _verified_login(self, client, email="refresh@example.com"):
        User.objects.create_user(email=email, password=STRONG_PASSWORD, name="R", email_verified=True)
        return login_user(client, email)

    def test_missing_header(self, api_client):
        self._verified_login(api_client)
        response = api_client.post("/api/auth/refresh/", format="json")
        assert_error_shape(response)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "missing_app_header"

    def test_rotate_and_blacklist_old(self, api_client):
        login = self._verified_login(api_client)
        old_refresh = login.cookies["refresh_token"].value
        refreshed = api_client.post("/api/auth/refresh/", format="json", **APP_HEADER)
        assert refreshed.status_code == 200
        assert "access" in refreshed.json()
        new_refresh = refreshed.cookies["refresh_token"].value
        assert new_refresh != old_refresh
        old_out = OutstandingToken.objects.filter(token=old_refresh).first()
        if old_out:
            assert BlacklistedToken.objects.filter(token=old_out).exists()

    def test_token_reuse_revokes_all(self, api_client):
        login = self._verified_login(api_client, "reuse@example.com")
        old_refresh = login.cookies["refresh_token"].value
        first = api_client.post("/api/auth/refresh/", format="json", **APP_HEADER)
        assert first.status_code == 200
        new_refresh = first.cookies["refresh_token"].value
        reuse = api_client.post(
            "/api/auth/refresh/",
            format="json",
            HTTP_COOKIE=f"refresh_token={old_refresh}",
            **APP_HEADER,
        )
        assert reuse.status_code == 401
        assert reuse.json()["error"]["code"] == "token_reused"
        dead = api_client.post(
            "/api/auth/refresh/",
            format="json",
            HTTP_COOKIE=f"refresh_token={new_refresh}",
            **APP_HEADER,
        )
        assert dead.status_code == 401

    def test_no_cookie(self, api_client):
        response = api_client.post("/api/auth/refresh/", format="json", **APP_HEADER)
        assert response.status_code == 401

    def test_garbage_cookie(self, api_client):
        response = api_client.post(
            "/api/auth/refresh/",
            format="json",
            HTTP_COOKIE="refresh_token=not-a-jwt",
            **APP_HEADER,
        )
        assert response.status_code == 401

    def test_logout_flow(self, api_client):
        login = self._verified_login(api_client, "logout@example.com")
        refresh_val = login.cookies["refresh_token"].value
        out = api_client.post("/api/auth/logout/", format="json", **APP_HEADER)
        assert out.status_code == 204
        out2 = api_client.post("/api/auth/logout/", format="json", **APP_HEADER)
        assert out2.status_code == 204
        again = api_client.post(
            "/api/auth/refresh/",
            format="json",
            HTTP_COOKIE=f"refresh_token={refresh_val}",
            **APP_HEADER,
        )
        assert again.status_code == 401

    def test_logout_missing_header(self, api_client):
        self._verified_login(api_client, "loh@example.com")
        response = api_client.post("/api/auth/logout/", format="json")
        assert response.json()["error"]["code"] == "missing_app_header"


@pytest.mark.django_db
class TestPasswordReset:
    RESET_MSG = "If an account exists with a verified email, you will receive password reset instructions."

    def test_same_response_variants(self, api_client):
        User.objects.create_user(email="verified@example.com", password=STRONG_PASSWORD, name="V", email_verified=True)
        User.objects.create_user(email="unv@example.com", password=STRONG_PASSWORD, name="U", email_verified=False)
        r1 = api_client.post("/api/auth/password-reset/", {"email": "verified@example.com"}, format="json")
        r2 = api_client.post("/api/auth/password-reset/", {"email": "nobody@example.com"}, format="json")
        r3 = api_client.post("/api/auth/password-reset/", {"email": "unv@example.com"}, format="json")
        assert r1.json() == r2.json() == r3.json()
        flush_outbound_to_mailbox()
        assert mail.outbox and len(mail.outbox) == 1

    def test_enqueue_failure_same_response_as_unknown(self, api_client, caplog):
        import logging

        User.objects.create_user(
            email="enqueuefail@example.com", password=STRONG_PASSWORD, name="E", email_verified=True
        )
        mail.outbox.clear()
        with caplog.at_level(logging.WARNING):
            with patch("accounts.services.enqueue_password_reset", side_effect=OutboxEnqueueError("secret-boom")):
                r_known = api_client.post("/api/auth/password-reset/", {"email": "enqueuefail@example.com"}, format="json")
                r_unknown = api_client.post("/api/auth/password-reset/", {"email": "ghost@example.com"}, format="json")
        assert r_known.status_code == r_unknown.status_code == 200
        assert r_known.json() == r_unknown.json()
        assert r_known.json()["message"] == self.RESET_MSG
        assert len(mail.outbox) == 0
        assert "accounts_outbox_enqueue_failed operation=password_reset" in caplog.text
        assert "enqueuefail@" not in caplog.text
        assert "secret-boom" not in caplog.text

    def test_confirm_and_revoke_refresh(self, api_client):
        user = User.objects.create_user(email="reset@example.com", password=STRONG_PASSWORD, name="R", email_verified=True)
        login_resp = login_user(api_client, "reset@example.com")
        stale_refresh = login_resp.cookies["refresh_token"].value
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        new_pass = "NewStrongPass88"
        confirm = api_client.post(
            "/api/auth/password-reset/confirm/",
            {"uid": uid, "token": token, "new_password": new_pass},
            format="json",
        )
        assert confirm.status_code == 200
        assert login_user(api_client, "reset@example.com", STRONG_PASSWORD).status_code == 401
        stale = api_client.post(
            "/api/auth/refresh/",
            format="json",
            HTTP_COOKIE=f"refresh_token={stale_refresh}",
            **APP_HEADER,
        )
        assert stale.status_code == 401
        assert login_user(api_client, "reset@example.com", new_pass).status_code == 200
        assert api_client.post("/api/auth/refresh/", format="json", **APP_HEADER).status_code == 200

    def test_reused_reset_token(self, api_client):
        user = User.objects.create_user(email="once@example.com", password=STRONG_PASSWORD, name="O", email_verified=True)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        payload = {"uid": uid, "token": token, "new_password": "AnotherGoodPass99"}
        assert api_client.post("/api/auth/password-reset/confirm/", payload, format="json").status_code == 200
        again = api_client.post("/api/auth/password-reset/confirm/", payload, format="json")
        assert again.status_code == 400
        assert again.json()["error"]["code"] == "invalid_token"

    def test_bad_uid_or_token(self, api_client):
        response = api_client.post(
            "/api/auth/password-reset/confirm/",
            {"uid": "bad", "token": "bad", "new_password": STRONG_PASSWORD},
            format="json",
        )
        assert response.json()["error"]["code"] == "invalid_token"

    def test_weak_password_keeps_token(self, api_client):
        user = User.objects.create_user(email="weak@example.com", password=STRONG_PASSWORD, name="W", email_verified=True)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        weak = api_client.post(
            "/api/auth/password-reset/confirm/",
            {"uid": uid, "token": token, "new_password": WEAK_PASSWORD},
            format="json",
        )
        assert weak.status_code == 400
        assert weak.json()["error"]["fields"]["new_password"]
        still_ok = api_client.post(
            "/api/auth/password-reset/confirm/",
            {"uid": uid, "token": token, "new_password": "ValidNewPass88"},
            format="json",
        )
        assert still_ok.status_code == 200


def resend_verification(client, email):
    return client.post("/api/auth/resend-verification/", {"email": email}, format="json")


@pytest.mark.django_db
class TestResendVerification:
    def test_no_email_sent_for_ineligible_accounts(self, api_client):
        User.objects.create_user(
            email="inactive@example.com", password=STRONG_PASSWORD, name="I", email_verified=False, is_active=False
        )
        User.objects.create_user(
            email="done@example.com", password=STRONG_PASSWORD, name="D", email_verified=True
        )
        mail.outbox.clear()
        r_unknown = resend_verification(api_client, "nobody@example.com")
        r_inactive = resend_verification(api_client, "inactive@example.com")
        r_verified = resend_verification(api_client, "done@example.com")
        assert r_unknown.status_code == r_inactive.status_code == r_verified.status_code == 200
        assert r_unknown.json() == r_inactive.json() == r_verified.json()
        assert len(mail.outbox) == 0

    def test_unverified_user_gets_verifiable_email(self, api_client):
        register_user(api_client, email="resend@example.com")
        user = User.objects.get(email="resend@example.com")
        assert user.email_verified is False
        flush_outbound_to_mailbox()
        mail.outbox.clear()
        response = resend_verification(api_client, "resend@example.com")
        assert response.status_code == 200
        flush_outbound_to_mailbox()
        assert len(mail.outbox) == 1
        verify = verify_from_outbox(api_client)
        assert verify.status_code == 200
        user.refresh_from_db()
        assert user.email_verified

    @pytest.mark.django_db(transaction=False)
    def test_cooldown_then_resend_after_cache_clear(self, api_client):
        from django.core.cache import cache

        register_user(api_client, email="cool@example.com")
        flush_outbound_to_mailbox()
        mail.outbox.clear()
        first = resend_verification(api_client, "cool@example.com")
        assert first.status_code == 200
        run_pending_on_commit_hooks()
        flush_outbound_to_mailbox()
        assert len(mail.outbox) == 1
        second = resend_verification(api_client, "cool@example.com")
        assert second.status_code == 200
        assert second.json() == first.json()
        flush_outbound_to_mailbox()
        assert len(mail.outbox) == 1
        cache.clear()
        assert resend_verification(api_client, "cool@example.com").status_code == 200
        flush_outbound_to_mailbox()
        assert len(mail.outbox) == 2

    def test_malformed_or_missing_email(self, api_client):
        missing = api_client.post("/api/auth/resend-verification/", {}, format="json")
        bad = resend_verification(api_client, "not-email")
        assert_error_shape(missing)
        assert_error_shape(bad)
        assert missing.status_code == bad.status_code == 400

    def test_unverified_and_unknown_same_body(self, api_client):
        register_user(api_client, email="parity@example.com")
        mail.outbox.clear()
        known = resend_verification(api_client, "parity@example.com")
        unknown = resend_verification(api_client, "missing@example.com")
        assert known.json() == unknown.json()

    def test_enqueue_failure_same_response_as_unknown(self, api_client, caplog):
        import logging

        register_user(api_client, email="resendfail@example.com")
        mail.outbox.clear()
        msg = "If an account exists and still needs verification, you will receive an email with a new link."
        with caplog.at_level(logging.WARNING):
            with patch("accounts.services.enqueue_verify_resend", side_effect=OutboxEnqueueError("no-leak")):
                r_known = resend_verification(api_client, "resendfail@example.com")
                r_unknown = resend_verification(api_client, "nobody-resend@example.com")
        assert r_known.status_code == r_unknown.status_code == 200
        assert r_known.json() == r_unknown.json()
        assert r_known.json()["message"] == msg
        assert len(mail.outbox) == 0
        assert "accounts_outbox_enqueue_failed operation=verify_resend" in caplog.text
        assert "resendfail@" not in caplog.text
        assert "no-leak" not in caplog.text
