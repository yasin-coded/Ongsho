"""Password-changed and password-reset-completed security emails via outbox."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.db import IntegrityError, transaction
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from audit.models import AuditLog
from core.mail_enqueue import OutboxEnqueueError
from core.models.outbound_email import OutboundEmail, OutboundEmailStatus, OutboundEmailType
from core.outbox.claim import claim_batch
from core.outbox.worker import process_claimed_row
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from tests.outbox_helpers import flush_outbound_to_mailbox
from tests.test_profile import (
    APP_HEADER,
    NEW_STRONG_PASSWORD,
    STRONG_PASSWORD,
    client_for,
    login_with_cookie,
    make_verified,
)
from tests.test_auth import login_user

User = get_user_model()


@pytest.mark.django_db
def test_password_change_queues_one_notice():
    user = make_verified("pwsec1@example.com")
    audit_before = AuditLog.objects.filter(user=user, action="password.changed").count()
    r = client_for(user).post(
        "/api/me/password/",
        {"current_password": STRONG_PASSWORD, "new_password": NEW_STRONG_PASSWORD},
        format="json",
    )
    assert r.status_code == 200
    assert AuditLog.objects.filter(user=user, action="password.changed").count() == audit_before + 1
    audit = AuditLog.objects.filter(user=user, action="password.changed").latest("id")
    row = OutboundEmail.objects.get(email_type=OutboundEmailType.PASSWORD_CHANGED)
    assert row.business_event_id == f"password_changed:{audit.pk}"
    assert row.user_id == user.pk
    assert row.to_email == user.email
    assert row.payload["audit_log_id"] == audit.pk


@pytest.mark.django_db
def test_password_reset_completed_queues_one_notice_and_audit():
    user = make_verified("pwsec2@example.com")
    api = APIClient()
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    r = api.post(
        "/api/auth/password-reset/confirm/",
        {"uid": uid, "token": token, "new_password": "AnotherGoodPass99"},
        format="json",
    )
    assert r.status_code == 200
    audit = AuditLog.objects.get(user=user, action="password.reset_completed")
    row = OutboundEmail.objects.get(email_type=OutboundEmailType.PASSWORD_RESET_COMPLETED)
    assert row.business_event_id == f"password_reset_completed:{audit.pk}"
    assert row.payload["audit_log_id"] == audit.pk


@pytest.mark.django_db
def test_password_change_revokes_tokens():
    user = make_verified("pwsec3@example.com")
    api = APIClient()
    login = login_user(api, user.email)
    stale = login.cookies["refresh_token"].value
    client_for(user).post(
        "/api/me/password/",
        {"current_password": STRONG_PASSWORD, "new_password": NEW_STRONG_PASSWORD},
        format="json",
    )
    outstanding = OutstandingToken.objects.filter(user=user)
    assert outstanding.exists()
    assert BlacklistedToken.objects.filter(token__in=outstanding).exists()
    assert (
        api.post(
            "/api/auth/refresh/",
            format="json",
            HTTP_COOKIE=f"refresh_token={stale}",
            **APP_HEADER,
        ).status_code
        == 401
    )


@pytest.mark.django_db
def test_password_change_enqueue_failure_does_not_rollback(caplog):
    user = make_verified("pwsec4@example.com")
    with caplog.at_level("WARNING"):
        with patch(
            "accounts.services.enqueue_password_changed_notice",
            side_effect=OutboxEnqueueError("boom"),
        ):
            r = client_for(user).post(
                "/api/me/password/",
                {"current_password": STRONG_PASSWORD, "new_password": NEW_STRONG_PASSWORD},
                format="json",
            )
    assert r.status_code == 200
    user.refresh_from_db()
    assert user.check_password(NEW_STRONG_PASSWORD)
    assert not OutboundEmail.objects.filter(email_type=OutboundEmailType.PASSWORD_CHANGED).exists()
    assert "accounts_security_email_enqueue_failed event=password_changed" in caplog.text
    assert "boom" not in caplog.text


@pytest.mark.django_db
def test_password_reset_enqueue_failure_still_succeeds(caplog):
    user = make_verified("pwsec5@example.com")
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    new_pass = "AnotherGoodPass99"
    with caplog.at_level("WARNING"):
        with patch(
            "accounts.services.enqueue_password_reset_completed_notice",
            side_effect=OutboxEnqueueError("boom"),
        ):
            r = APIClient().post(
                "/api/auth/password-reset/confirm/",
                {"uid": uid, "token": token, "new_password": new_pass},
                format="json",
            )
    assert r.status_code == 200
    user.refresh_from_db()
    assert user.check_password(new_pass)
    assert AuditLog.objects.filter(user=user, action="password.reset_completed").exists()
    assert not OutboundEmail.objects.filter(
        email_type=OutboundEmailType.PASSWORD_RESET_COMPLETED
    ).exists()
    assert "accounts_security_email_enqueue_failed event=password_reset_completed" in caplog.text


@pytest.mark.django_db
def test_no_sync_send_on_password_change():
    user = make_verified("pwsec6@example.com")
    with patch("accounts.emails.send_password_changed_notice_email") as send_mock:
        client_for(user).post(
            "/api/me/password/",
            {"current_password": STRONG_PASSWORD, "new_password": NEW_STRONG_PASSWORD},
            format="json",
        )
    send_mock.assert_not_called()


@pytest.mark.django_db
def test_invalid_reset_token_no_completion_notice():
    user = make_verified("pwsec7@example.com")
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    r = APIClient().post(
        "/api/auth/password-reset/confirm/",
        {"uid": uid, "token": "bad-token", "new_password": "AnotherGoodPass99"},
        format="json",
    )
    assert r.status_code == 400
    assert not OutboundEmail.objects.filter(
        email_type=OutboundEmailType.PASSWORD_RESET_COMPLETED
    ).exists()
    assert not AuditLog.objects.filter(user=user, action="password.reset_completed").exists()


@pytest.mark.django_db
def test_reused_reset_token_single_completion_notice():
    user = make_verified("pwsec8@example.com")
    api = APIClient()
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    payload = {"uid": uid, "token": token, "new_password": "AnotherGoodPass99"}
    assert api.post("/api/auth/password-reset/confirm/", payload, format="json").status_code == 200
    assert api.post("/api/auth/password-reset/confirm/", payload, format="json").status_code == 400
    assert (
        OutboundEmail.objects.filter(email_type=OutboundEmailType.PASSWORD_RESET_COMPLETED).count()
        == 1
    )


@pytest.mark.django_db
def test_password_reset_request_still_uses_password_reset_type():
    user = make_verified("pwsec9@example.com")
    r = APIClient().post("/api/auth/password-reset/", {"email": user.email}, format="json")
    assert r.status_code == 200
    row = OutboundEmail.objects.get(user=user, email_type=OutboundEmailType.PASSWORD_RESET)
    assert row.business_event_id.startswith(f"password_reset:{user.pk}:")


def _claim_row(row):
    claims = claim_batch(batch_size=1, worker_id="pytest-pwsec")
    assert claims
    _row_id, token = claims[0]
    return row, token


@pytest.mark.django_db
def test_dispatch_success_password_changed(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    user = make_verified("pwsecd@example.com")
    client_for(user).post(
        "/api/me/password/",
        {"current_password": STRONG_PASSWORD, "new_password": NEW_STRONG_PASSWORD},
        format="json",
    )
    mail.outbox.clear()
    flush_outbound_to_mailbox()
    assert len(mail.outbox) == 1
    assert "password was changed" in mail.outbox[0].subject.lower()


@pytest.mark.django_db
def test_dispatch_inactive_user_cancelled(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    user = make_verified("pwsecin@example.com")
    client_for(user).post(
        "/api/me/password/",
        {"current_password": STRONG_PASSWORD, "new_password": NEW_STRONG_PASSWORD},
        format="json",
    )
    row = OutboundEmail.objects.get(email_type=OutboundEmailType.PASSWORD_CHANGED)
    row, token = _claim_row(row)
    user.is_active = False
    user.save(update_fields=["is_active"])
    with patch("accounts.emails.send_password_changed_notice_email") as send_mock:
        outcome = process_claimed_row(row_id=row.pk, claim_token=token)
    assert outcome == "cancelled"
    row.refresh_from_db()
    assert row.last_error_code == "user_inactive"
    send_mock.assert_not_called()


@pytest.mark.django_db
def test_dispatch_unverified_cancelled(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    user = make_verified("pwsecuv@example.com")
    client_for(user).post(
        "/api/me/password/",
        {"current_password": STRONG_PASSWORD, "new_password": NEW_STRONG_PASSWORD},
        format="json",
    )
    row = OutboundEmail.objects.get(email_type=OutboundEmailType.PASSWORD_CHANGED)
    row, token = _claim_row(row)
    user.email_verified = False
    user.save(update_fields=["email_verified"])
    with patch("accounts.emails.send_password_changed_notice_email") as send_mock:
        outcome = process_claimed_row(row_id=row.pk, claim_token=token)
    assert outcome == "cancelled"
    row.refresh_from_db()
    assert row.last_error_code == "email_not_verified"
    send_mock.assert_not_called()


@pytest.mark.django_db
def test_dispatch_recipient_mismatch_fails(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    user = make_verified("pwsecm@example.com")
    client_for(user).post(
        "/api/me/password/",
        {"current_password": STRONG_PASSWORD, "new_password": NEW_STRONG_PASSWORD},
        format="json",
    )
    row = OutboundEmail.objects.get(email_type=OutboundEmailType.PASSWORD_CHANGED)
    row, token = _claim_row(row)
    row.to_email = "other@example.com"
    row.save(update_fields=["to_email", "updated_at"])
    with patch("accounts.emails.send_password_changed_notice_email") as send_mock:
        outcome = process_claimed_row(row_id=row.pk, claim_token=token)
    assert outcome == "failed"
    row.refresh_from_db()
    assert row.last_error_code == "recipient_mismatch"
    send_mock.assert_not_called()


@pytest.mark.django_db
def test_duplicate_audit_event_id_idempotent():
    user = make_verified("pwsecid@example.com")
    from core.mail_outbox import enqueue_password_changed_notice

    audit = AuditLog.objects.create(
        user=user,
        action="password.changed",
        entity_type="User",
        entity_id=user.pk,
        old_value=None,
        new_value=None,
    )
    with transaction.atomic():
        enqueue_password_changed_notice(user=user, audit_log_id=audit.pk)
    with transaction.atomic():
        with pytest.raises(IntegrityError):
            enqueue_password_changed_notice(user=user, audit_log_id=audit.pk)
    assert (
        OutboundEmail.objects.filter(
            business_event_id=f"password_changed:{audit.pk}",
        ).count()
        == 1
    )