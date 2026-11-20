import re
import time
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail, signing
from rest_framework.test import APIClient

from accounts.cookies import REFRESH_COOKIE_NAME
from accounts.tokens import EMAIL_CHANGE_SALT, make_email_change_token
from audit.models import AuditLog
from tests.outbox_helpers import flush_outbound_to_mailbox

User = get_user_model()

STRONG_PASSWORD = "HorseBatteryStaple99"
NEW_STRONG_PASSWORD = "CorrectHorseBattery88"
WEAK_PASSWORD = "123"
APP_HEADER = {"HTTP_X_REQUESTED_WITH": "Ongsho"}

PROFILE_FIELDS = frozenset(
    {"id", "email", "name", "avatar_id", "email_verified", "pending_email", "plans_owned", "plans_joined"}
)

ME_ENDPOINTS = [
    ("/api/me/", "get"),
    ("/api/me/", "patch"),
    ("/api/me/password/", "post"),
    ("/api/me/email/", "post"),
    ("/api/me/email/verify/", "post"),
    ("/api/me/email/resend/", "post"),
    ("/api/me/nav-counts/", "get"),
    ("/api/me/email/", "delete"),
]

FORBIDDEN_PATCH_FIELDS = (
    "email",
    "pending_email",
    "email_verified",
    "is_staff",
    "is_superuser",
    "is_active",
    "password",
    "id",
)


@pytest.fixture(autouse=True)
def profile_env(settings):
    settings.FRONTEND_BASE_URL = "http://localhost:5173"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "noreply@example.com"
    settings.REFRESH_COOKIE_SECURE = False
    settings.REFRESH_COOKIE_SAMESITE = "Lax"


def assert_error_shape(response):
    assert response.status_code >= 400
    data = response.json()
    assert set(data) == {"error"}
    assert set(data["error"]) == {"code", "message", "fields"}


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def make_verified(email, password=STRONG_PASSWORD, name="Test User", **extra):
    return User.objects.create_user(
        email=email,
        password=password,
        name=name,
        email_verified=True,
        **extra,
    )


def login_with_cookie(client, email, password=STRONG_PASSWORD):
    return client.post("/api/auth/login/", {"email": email, "password": password}, format="json")


def extract_email_change_token(message_body: str) -> str:
    match = re.search(r"type=email-change&token=([^\s]+)", message_body)
    assert match, message_body
    return match.group(1)


def request_email_change(client, new_email, password=STRONG_PASSWORD):
    response = client.post(
        "/api/me/email/",
        {"new_email": new_email, "password": password},
        format="json",
    )
    if response.status_code == 200:
        flush_outbound_to_mailbox()
    return response


@pytest.mark.django_db
@pytest.mark.parametrize("path,method", ME_ENDPOINTS)
def test_me_endpoints_anonymous_401(path, method):
    client = APIClient()
    call = getattr(client, method)
    if method == "patch":
        response = call(path, {"name": "X"}, format="json")
    elif method == "post":
        response = call(path, {}, format="json")
    else:
        response = call(path)
    assert response.status_code == 401
    assert_error_shape(response)


@pytest.mark.django_db
class TestGetProfile:
    def test_exact_fields_and_isolation(self):
        u1 = make_verified("one@example.com", name="One")
        u2 = make_verified("two@example.com", name="Two", is_staff=True)
        u1.is_superuser = False
        u1.save()
        r1 = client_for(u1).get("/api/me/")
        r2 = client_for(u2).get("/api/me/")
        assert r1.status_code == r2.status_code == 200
        assert set(r1.json().keys()) == PROFILE_FIELDS
        assert r1.json()["email"] == "one@example.com"
        assert r2.json()["email"] == "two@example.com"
        for key in ("password", "is_staff", "is_superuser", "last_login"):
            assert key not in r1.json()
            assert key not in r2.json()


@pytest.mark.django_db
class TestPatchProfile:
    def test_name_and_avatar(self):
        user = make_verified("patch@example.com")
        client = client_for(user)
        response = client.patch("/api/me/", {"name": "  Patched  ", "avatar_id": "avatar_3"}, format="json")
        assert response.status_code == 200
        assert response.json()["name"] == "Patched"
        assert response.json()["avatar_id"] == "avatar_3"
        user.refresh_from_db()
        assert user.name == "Patched"
        assert AuditLog.objects.filter(user=user, action="profile.updated").count() == 1

    def test_invalid_name_cases(self):
        client = client_for(make_verified("badname@example.com"))
        long_name = "x" * 256
        for payload in ({"name": ""}, {"name": "   "}, {"name": long_name}):
            response = client.patch("/api/me/", payload, format="json")
            assert_error_shape(response)
            assert response.status_code == 400

    def test_invalid_avatar(self):
        client = client_for(make_verified("badav@example.com"))
        response = client.patch("/api/me/", {"avatar_id": "avatar_99"}, format="json")
        assert_error_shape(response)
        assert response.status_code == 400

    @pytest.mark.parametrize("field", FORBIDDEN_PATCH_FIELDS)
    def test_forbidden_fields(self, field):
        user = make_verified("forbid@example.com")
        client = client_for(user)
        before_name = user.name
        response = client.patch("/api/me/", {field: "hacked"}, format="json")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "field_not_editable"
        assert field in response.json()["error"]["fields"]
        user.refresh_from_db()
        assert user.name == before_name
        assert AuditLog.objects.filter(user=user, action="profile.updated").count() == 0

    def test_put_405(self):
        response = client_for(make_verified("put@example.com")).put("/api/me/", {}, format="json")
        assert response.status_code == 405
        assert_error_shape(response)

    def test_no_op_no_audit(self):
        user = make_verified("noop@example.com", name="Same")
        client = client_for(user)
        before = AuditLog.objects.count()
        same = client.patch("/api/me/", {"name": "Same"}, format="json")
        empty = client.patch("/api/me/", {}, format="json")
        assert same.status_code == empty.status_code == 200
        assert AuditLog.objects.count() == before


@pytest.mark.django_db
class TestPasswordChange:
    def test_success_and_login(self):
        user = make_verified("pw@example.com")
        client = client_for(user)
        login = login_with_cookie(APIClient(), "pw@example.com")
        refresh_before = login.cookies[REFRESH_COOKIE_NAME].value
        response = client.post(
            "/api/me/password/",
            {"current_password": STRONG_PASSWORD, "new_password": NEW_STRONG_PASSWORD},
            format="json",
        )
        assert response.status_code == 200
        user.refresh_from_db()
        assert user.check_password(NEW_STRONG_PASSWORD)
        assert not user.check_password(STRONG_PASSWORD)
        assert REFRESH_COOKIE_NAME in response.cookies
        assert response.cookies[REFRESH_COOKIE_NAME].value == ""
        refreshed = APIClient().post(
            "/api/auth/refresh/",
            format="json",
            HTTP_COOKIE=f"{REFRESH_COOKIE_NAME}={refresh_before}",
            **APP_HEADER,
        )
        assert refreshed.status_code == 401
        assert login_with_cookie(APIClient(), "pw@example.com", NEW_STRONG_PASSWORD).status_code == 200
        assert login_with_cookie(APIClient(), "pw@example.com", STRONG_PASSWORD).status_code == 401

    def test_wrong_current_password(self):
        client = client_for(make_verified("pwwrong@example.com"))
        response = client.post(
            "/api/me/password/",
            {"current_password": "nope", "new_password": NEW_STRONG_PASSWORD},
            format="json",
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_password"
        assert "password" in response.json()["error"]["fields"]

    def test_weak_new_password(self):
        client = client_for(make_verified("pwweak@example.com"))
        response = client.post(
            "/api/me/password/",
            {"current_password": STRONG_PASSWORD, "new_password": WEAK_PASSWORD},
            format="json",
        )
        assert_error_shape(response)
        assert response.status_code == 400
        assert "new_password" in response.json()["error"]["fields"]

    def test_missing_fields(self):
        client = client_for(make_verified("pwmiss@example.com"))
        assert_error_shape(client.post("/api/me/password/", {}, format="json"))

    def test_other_user_tokens_unaffected(self):
        victim = make_verified("victim@example.com")
        bystander = make_verified("bystander@example.com")
        by_login = login_with_cookie(APIClient(), "bystander@example.com")
        by_refresh = by_login.cookies[REFRESH_COOKIE_NAME].value
        client_for(victim).post(
            "/api/me/password/",
            {"current_password": STRONG_PASSWORD, "new_password": NEW_STRONG_PASSWORD},
            format="json",
        )
        still = APIClient().post(
            "/api/auth/refresh/",
            format="json",
            HTTP_COOKIE=f"{REFRESH_COOKIE_NAME}={by_refresh}",
            **APP_HEADER,
        )
        assert still.status_code == 200

    def test_audit_has_no_password_text(self):
        user = make_verified("pwaudit@example.com")
        client_for(user).post(
            "/api/me/password/",
            {"current_password": STRONG_PASSWORD, "new_password": NEW_STRONG_PASSWORD},
            format="json",
        )
        row = AuditLog.objects.get(user=user, action="password.changed")
        dumped = str(row.old_value) + str(row.new_value)
        assert STRONG_PASSWORD not in dumped
        assert NEW_STRONG_PASSWORD not in dumped


@pytest.mark.django_db
class TestEmailChangeRequest:
    def test_wrong_password(self):
        user = make_verified("ecwrong@example.com")
        client = client_for(user)
        response = request_email_change(client, "new@example.com", password="bad")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_password"
        user.refresh_from_db()
        assert user.pending_email == ""

    def test_same_invalid_and_taken(self):
        user = make_verified("ecval@example.com")
        make_verified("taken@example.com")
        client = client_for(user)
        same = request_email_change(client, "ecval@example.com")
        assert_error_shape(same)
        assert "new_email" in same.json()["error"]["fields"]
        bad = request_email_change(client, "not-an-email")
        assert_error_shape(bad)
        taken = request_email_change(client, "Taken@Example.com")
        assert_error_shape(taken)
        assert taken.json()["error"]["fields"]["new_email"]

    def test_success_mail_and_login(self):
        user = make_verified("ecok@example.com")
        client = client_for(user)
        mail.outbox.clear()
        response = request_email_change(client, "fresh@example.com")
        assert response.status_code == 200
        user.refresh_from_db()
        assert user.pending_email == "fresh@example.com"
        assert user.email == "ecok@example.com"
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["fresh@example.com"]
        assert settings.FRONTEND_BASE_URL in mail.outbox[0].body
        assert "type=email-change" in mail.outbox[0].body
        assert login_with_cookie(APIClient(), "ecok@example.com").status_code == 200
        assert login_with_cookie(APIClient(), "fresh@example.com").status_code == 401

    def test_second_request_replaces_token(self):
        user = make_verified("ec2@example.com")
        client = client_for(user)
        mail.outbox.clear()
        request_email_change(client, "first-new@example.com")
        token_first = extract_email_change_token(mail.outbox[0].body)
        mail.outbox.clear()
        request_email_change(client, "second-new@example.com")
        assert user.refresh_from_db() or True
        user.refresh_from_db()
        assert user.pending_email == "second-new@example.com"
        bad = client.post("/api/me/email/verify/", {"token": token_first}, format="json")
        assert bad.status_code == 400
        assert bad.json()["error"]["code"] == "invalid_token"


@pytest.mark.django_db
class TestEmailChangeVerify:
    def _pending(self, email="verify@example.com", pending="verify-new@example.com"):
        user = make_verified(email)
        client = client_for(user)
        mail.outbox.clear()
        request_email_change(client, pending)
        token = extract_email_change_token(mail.outbox[0].body)
        return user, client, token, pending

    def test_success_flow(self):
        user, client, token, pending = self._pending()
        login = login_with_cookie(APIClient(), "verify@example.com")
        refresh_before = login.cookies[REFRESH_COOKIE_NAME].value
        response = client.post("/api/me/email/verify/", {"token": token}, format="json")
        assert response.status_code == 200
        assert response.json()["email"] == pending
        user.refresh_from_db()
        assert user.email == pending
        assert user.pending_email == ""
        assert user.email_verified is True
        refreshed = APIClient().post(
            "/api/auth/refresh/",
            format="json",
            HTTP_COOKIE=f"{REFRESH_COOKIE_NAME}={refresh_before}",
            **APP_HEADER,
        )
        assert refreshed.status_code == 401
        assert REFRESH_COOKIE_NAME in response.cookies
        assert login_with_cookie(APIClient(), pending).status_code == 200
        assert login_with_cookie(APIClient(), "verify@example.com").status_code == 401

    def test_anonymous_401(self):
        response = APIClient().post("/api/me/email/verify/", {"token": "x"}, format="json")
        assert response.status_code == 401
        assert_error_shape(response)

    def test_another_user_token(self):
        user_a = make_verified("a@example.com")
        user_b = make_verified("b@example.com")
        client_b = client_for(user_b)
        request_email_change(client_b, "b-new@example.com")
        token_b = extract_email_change_token(mail.outbox[-1].body)
        response = client_for(user_a).post("/api/me/email/verify/", {"token": token_b}, format="json")
        assert response.json()["error"]["code"] == "invalid_token"

    def test_garbage_and_expired(self):
        user, client, _, _ = self._pending()
        garbage = client.post("/api/me/email/verify/", {"token": "garbage"}, format="json")
        assert garbage.json()["error"]["code"] == "invalid_token"
        payload = signing.dumps(
            {"user_id": user.pk, "email": "verify-new@example.com"},
            salt=EMAIL_CHANGE_SALT,
        )
        future = time.time() + int(timedelta(days=5).total_seconds())
        with patch("django.core.signing.time.time", return_value=future):
            expired = client.post("/api/me/email/verify/", {"token": payload}, format="json")
        assert expired.json()["error"]["code"] == "invalid_token"

    def test_audit_rows_and_idempotent(self):
        user, client, token, pending = self._pending()
        assert AuditLog.objects.filter(user=user, action="email_change.requested").count() == 1
        client.post("/api/me/email/verify/", {"token": token}, format="json")
        verified = AuditLog.objects.get(user=user, action="email_change.verified")
        assert verified.old_value == {"email": "verify@example.com"}
        assert verified.new_value == {"email": pending}
        total = AuditLog.objects.filter(user=user).count()
        again = client.post("/api/me/email/verify/", {"token": token}, format="json")
        assert again.status_code == 200
        assert AuditLog.objects.filter(user=user).count() == total

    def test_email_taken_race(self):
        user, client, token, pending = self._pending(pending="race@example.com")
        make_verified("race@example.com")
        response = client.post("/api/me/email/verify/", {"token": token}, format="json")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "email_taken"
        user.refresh_from_db()
        assert user.email == "verify@example.com"
        assert user.pending_email == "race@example.com"


@pytest.mark.django_db
class TestEmailChangeCancel:
    def test_cancel_clears_and_invalidates_token(self):
        user = make_verified("cancel@example.com")
        client = client_for(user)
        request_email_change(client, "cancel-new@example.com")
        token = extract_email_change_token(mail.outbox[-1].body)
        first = client.delete("/api/me/email/")
        second = client.delete("/api/me/email/")
        assert first.status_code == second.status_code == 204
        user.refresh_from_db()
        assert user.pending_email == ""
        bad = client.post("/api/me/email/verify/", {"token": token}, format="json")
        assert bad.json()["error"]["code"] == "invalid_token"
        assert AuditLog.objects.filter(user=user, action="email_change.cancelled").count() == 1
