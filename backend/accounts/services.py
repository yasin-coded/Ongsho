from __future__ import annotations

import hashlib
import logging
import secrets

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken, UntypedToken

from audit import services as audit_services
from accounts.constants import DEFAULT_AVATAR_ID
from accounts import selectors as account_selectors
from core.mail_enqueue import OutboxEnqueueError, OutboxPayloadError
from core.mail_outbox import (
    cancel_pending_account_notification_deliveries,
    cancel_pending_email_change_deliveries,
    cancel_pending_reminder_deliveries_for_user,
    enqueue_account_verify,
    enqueue_email_change,
    enqueue_email_changed_new_notice,
    enqueue_email_changed_previous_notice,
    enqueue_password_changed_notice,
    enqueue_password_reset,
    enqueue_password_reset_completed_notice,
    enqueue_verify_resend,
)
from core.outbox.verification import cancel_pending_verification_deliveries
from accounts.tokens import load_email_change_token, load_email_verification_token
from core.exceptions import ConflictError, Forbidden, Unauthorized, ValidationFailed
from core.lockout import (
    assert_login_allowed,
    assert_password_confirm_allowed,
    clear_login_success,
    clear_password_confirm_success,
    record_login_failure,
    record_password_confirm_failure,
)

User = get_user_model()

logger = logging.getLogger(__name__)

CLOSED_ACCOUNT_DISPLAY_NAME = "Closed account"
ACCOUNT_TOMBSTONE_DOMAIN = "closed.ongsho.invalid"

PASSWORD_RESET_GENERIC_MESSAGE = (
    "If an account exists with a verified email, you will receive password reset instructions."
)
REGISTER_MESSAGE = "Check your email to verify your account before signing in."
RESEND_VERIFICATION_MESSAGE = (
    "If an account exists and still needs verification, you will receive an email with a new link."
)
RESEND_VERIFICATION_COOLDOWN_SECONDS = 60
_RESEND_VERIFY_CACHE_PREFIX = "accounts:resend-verify:"

_DUPLICATE_EMAIL_CONSTRAINTS = frozenset(
    {
        "accounts_user_email_ci_unique",
        "accounts_user_email_key",
    }
)
_DUPLICATE_EMAIL_VALIDATION = ValidationFailed(
    "A user with this email already exists.",
    fields={"email": ["A user with this email already exists."]},
    code="validation_failed",
)


def _integrity_error_is_duplicate_email(exc: IntegrityError) -> bool:
    diag = getattr(getattr(exc, "__cause__", None), "diag", None)
    constraint = getattr(diag, "constraint_name", None)
    if constraint in _DUPLICATE_EMAIL_CONSTRAINTS:
        return True
    text = str(exc).lower()
    return any(name in text for name in _DUPLICATE_EMAIL_CONSTRAINTS)


def _best_effort_enqueue_password_changed(user, *, audit_log_id: int) -> None:
    try:
        with transaction.atomic():
            enqueue_password_changed_notice(user=user, audit_log_id=audit_log_id)
    except (OutboxEnqueueError, OutboxPayloadError, IntegrityError):
        logger.warning(
            "accounts_security_email_enqueue_failed event=password_changed user_id=%s audit_log_id=%s",
            user.pk,
            audit_log_id,
        )


def _best_effort_enqueue_email_change_completion(
    user,
    *,
    audit_log_id: int,
    previous_email: str,
    new_email: str,
) -> None:
    for event, enqueue_fn in (
        (
            "email_changed_new",
            lambda: enqueue_email_changed_new_notice(
                user=user,
                audit_log_id=audit_log_id,
                previous_email=previous_email,
                new_email=new_email,
            ),
        ),
        (
            "email_changed_previous",
            lambda: enqueue_email_changed_previous_notice(
                user=user,
                audit_log_id=audit_log_id,
                previous_email=previous_email,
                new_email=new_email,
            ),
        ),
    ):
        try:
            with transaction.atomic():
                enqueue_fn()
        except (OutboxEnqueueError, OutboxPayloadError, IntegrityError):
            logger.warning(
                "accounts_email_change_notice_enqueue_failed event=%s user_id=%s audit_log_id=%s",
                event,
                user.pk,
                audit_log_id,
            )


def _best_effort_enqueue_password_reset_completed(user, *, audit_log_id: int) -> None:
    try:
        with transaction.atomic():
            enqueue_password_reset_completed_notice(user=user, audit_log_id=audit_log_id)
    except (OutboxEnqueueError, OutboxPayloadError, IntegrityError):
        logger.warning(
            "accounts_security_email_enqueue_failed event=password_reset_completed user_id=%s audit_log_id=%s",
            user.pk,
            audit_log_id,
        )


def verify_current_password(user, password: str) -> None:
    assert_password_confirm_allowed(user.pk)
    if not password:
        raise ValidationFailed(
            "Enter your password.",
            code="invalid_password",
            fields={"password": ["Enter your password."]},
        )
    if not user.check_password(password):
        record_password_confirm_failure(user.pk)
        raise ValidationFailed(
            "The password is not correct.",
            code="invalid_password",
            fields={"password": ["The password is not correct."]},
        )
    clear_password_confirm_success(user.pk)


@transaction.atomic
def register_user(*, email: str, password: str, name: str) -> User:
    if User.objects.filter(email__iexact=email).exists():
        raise _DUPLICATE_EMAIL_VALIDATION
    try:
        with transaction.atomic():
            user = User.objects.create_user(
                email=email,
                password=password,
                name=name,
                email_verified=False,
                avatar_id=DEFAULT_AVATAR_ID,
            )
            enqueue_account_verify(user)
    except IntegrityError as exc:
        if _integrity_error_is_duplicate_email(exc):
            raise _DUPLICATE_EMAIL_VALIDATION from exc
        raise
    return user


def _resend_verification_cache_key(email: str) -> str:
    digest = hashlib.sha256(email.lower().encode("utf-8")).hexdigest()
    return f"{_RESEND_VERIFY_CACHE_PREFIX}{digest}"


@transaction.atomic
def resend_verification(email: str) -> None:
    user = (
        User.objects.select_for_update()
        .filter(email__iexact=email, is_active=True, email_verified=False)
        .first()
    )
    if not user:
        return
    cache_key = _resend_verification_cache_key(email)
    if cache.get(cache_key):
        return
    enqueue_verify_resend(user)
    transaction.on_commit(
        lambda key=cache_key: cache.set(key, True, timeout=RESEND_VERIFICATION_COOLDOWN_SECONDS)
    )


def verify_email(token: str) -> None:
    try:
        payload = load_email_verification_token(token)
    except Exception:
        raise ValidationFailed("Invalid or expired verification link.", code="invalid_token")

    user_id = payload.get("user_id")
    email = payload.get("email")
    user = User.objects.filter(pk=user_id).first()
    if not user or user.email != email:
        raise ValidationFailed("Invalid or expired verification link.", code="invalid_token")

    if not user.email_verified:
        user.email_verified = True
        user.save(update_fields=["email_verified"])


def login_user(*, email: str, password: str, client_ip: str = "") -> tuple[str, str, User]:
    from django.contrib.auth.hashers import check_password

    from core.lockout import DUMMY_LOGIN_PASSWORD_HASH, LOGIN_INVALID_MESSAGE

    assert_login_allowed(email=email, ip=client_ip)
    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        check_password(password, DUMMY_LOGIN_PASSWORD_HASH)
        record_login_failure(email=email, ip=client_ip)
        raise Unauthorized(
            LOGIN_INVALID_MESSAGE,
            code="invalid_credentials",
        )
    if not user.is_active:
        check_password(password, user.password)
        record_login_failure(email=email, ip=client_ip)
        raise Unauthorized(
            LOGIN_INVALID_MESSAGE,
            code="invalid_credentials",
        )
    if not check_password(password, user.password):
        check_password(password, DUMMY_LOGIN_PASSWORD_HASH)
        record_login_failure(email=email, ip=client_ip)
        raise Unauthorized(
            LOGIN_INVALID_MESSAGE,
            code="invalid_credentials",
        )
    if not user.email_verified:
        raise Forbidden(
            "Verify your email before signing in.",
            code="email_not_verified",
        )
    clear_login_success(email=email, ip=client_ip)
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token), str(refresh), user


def _reuse_or_invalid(refresh_raw: str) -> None:
    try:
        untyped = UntypedToken(refresh_raw)
    except TokenError:
        raise Unauthorized("Refresh token is missing or invalid.", code="invalid_token") from None

    jti = untyped.get("jti")
    user_id = untyped.get("user_id")
    outstanding = OutstandingToken.objects.filter(jti=jti).first()
    if outstanding and BlacklistedToken.objects.filter(token=outstanding).exists():
        user = User.objects.filter(pk=user_id).first()
        if user:
            revoke_all_tokens(user)
        raise Unauthorized("Refresh token was already used.", code="token_reused")
    raise Unauthorized("Refresh token is missing or invalid.", code="invalid_token")


def rotate_refresh(refresh_raw: str | None) -> tuple[str, str]:
    if not refresh_raw:
        raise Unauthorized("Refresh token is missing or invalid.", code="invalid_token")

    try:
        old = RefreshToken(refresh_raw)
    except TokenError:
        _reuse_or_invalid(refresh_raw)

    user_id = old.get("user_id")
    user = User.objects.filter(pk=user_id).first()

    outstanding = OutstandingToken.objects.filter(jti=old["jti"]).first()
    if outstanding and BlacklistedToken.objects.filter(token=outstanding).exists():
        if user:
            revoke_all_tokens(user)
        raise Unauthorized("Refresh token was already used.", code="token_reused")

    if not user or not user.is_active or not user.email_verified:
        raise Unauthorized("Refresh token is missing or invalid.", code="invalid_token")

    old.blacklist()
    new_refresh = RefreshToken.for_user(user)
    return str(new_refresh.access_token), str(new_refresh)


def logout_refresh(refresh_raw: str | None) -> None:
    if not refresh_raw:
        return
    try:
        token = RefreshToken(refresh_raw)
        token.blacklist()
    except TokenError:
        return


@transaction.atomic
def request_password_reset(email: str) -> None:
    user = User.objects.filter(email__iexact=email, is_active=True, email_verified=True).first()
    if not user:
        return
    enqueue_password_reset(user)


@transaction.atomic
def confirm_password_reset(*, uid: str, token: str, new_password: str) -> None:
    user = _user_from_uid(uid)
    if user is None or not default_token_generator.check_token(user, token):
        raise ValidationFailed("Invalid or expired reset link.", code="invalid_token")

    user = User.objects.select_for_update().get(pk=user.pk)
    user.set_password(new_password)
    user.save(update_fields=["password"])
    audit_row = audit_services.log(
        user,
        "password.reset_completed",
        "User",
        user.pk,
        None,
        None,
    )
    revoke_all_tokens(user)
    _best_effort_enqueue_password_reset_completed(user, audit_log_id=audit_row.pk)


def _user_from_uid(uid: str):
    try:
        user_id = int(urlsafe_base64_decode(uid).decode())
    except (TypeError, ValueError, OverflowError):
        return None
    return User.objects.filter(pk=user_id).first()


def user_for_password_reset_check(uid: str, token: str):
    user = _user_from_uid(uid)
    if user is None or not default_token_generator.check_token(user, token):
        raise ValidationFailed("Invalid or expired reset link.", code="invalid_token")
    return user


@transaction.atomic
def revoke_all_tokens(user) -> None:
    for outstanding in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=outstanding)


def profile_dict(user) -> dict:
    from accounts import selectors as account_selectors

    return {
        "id": user.pk,
        "email": user.email,
        "name": user.name,
        "avatar_id": user.avatar_id,
        "email_verified": user.email_verified,
        "pending_email": user.pending_email,
        "plans_owned": account_selectors.plans_owned_count(user),
        "plans_joined": account_selectors.plans_joined_count(user),
    }


RESEND_EMAIL_CHANGE_COOLDOWN_SECONDS = 60
_RESEND_EMAIL_CHANGE_CACHE_PREFIX = "accounts:resend-email-change:"


def _resend_email_change_cache_key(user_id: int) -> str:
    return f"{_RESEND_EMAIL_CHANGE_CACHE_PREFIX}{user_id}"


@transaction.atomic
def resend_pending_email_change(user) -> None:
    user = User.objects.select_for_update().get(pk=user.pk)
    if not user.pending_email:
        raise ValidationFailed(
            "No pending email change.",
            code="nothing_pending",
        )
    cache_key = _resend_email_change_cache_key(user.pk)
    if cache.get(cache_key):
        return
    enqueue_email_change(user)
    transaction.on_commit(
        lambda key=cache_key: cache.set(key, True, timeout=RESEND_EMAIL_CHANGE_COOLDOWN_SECONDS)
    )


def reminder_settings_dict(user) -> dict:
    from accounts.validators import parse_reminder_days

    return {
        "days_before": parse_reminder_days(user.reminder_days),
        "email": user.email_reminders,
    }


@transaction.atomic
def update_reminder_settings(user, *, days_before=None, email=None) -> None:
    from accounts.validators import format_reminder_days

    user = User.objects.select_for_update().get(pk=user.pk)
    update_fields: list[str] = []
    if days_before is not None:
        user.reminder_days = format_reminder_days(days_before)
        update_fields.append("reminder_days")
    if email is not None:
        user.email_reminders = email
        update_fields.append("email_reminders")
    if update_fields:
        user.full_clean()
        user.save(update_fields=update_fields)
        if email is False:
            from core.mail_outbox import cancel_pending_reminder_deliveries_for_user

            cancel_pending_reminder_deliveries_for_user(user.pk)
        if email is False:
            from core.mail_outbox import cancel_pending_reminder_deliveries_for_user

            cancel_pending_reminder_deliveries_for_user(user.pk)


@transaction.atomic
def update_profile(user, validated: dict):
    user = User.objects.select_for_update().get(pk=user.pk)
    old_snapshot: dict = {}
    new_snapshot: dict = {}
    update_fields: list[str] = []

    if "name" in validated:
        name = validated["name"]
        if name != user.name:
            old_snapshot["name"] = user.name
            new_snapshot["name"] = name
            user.name = name
            update_fields.append("name")

    if "avatar_id" in validated:
        avatar_id = validated["avatar_id"]
        if avatar_id != user.avatar_id:
            old_snapshot["avatar_id"] = user.avatar_id
            new_snapshot["avatar_id"] = avatar_id
            user.avatar_id = avatar_id
            update_fields.append("avatar_id")

    if not update_fields:
        return user

    user.save(update_fields=update_fields)
    audit_services.log(user, "profile.updated", "User", user.pk, old_snapshot, new_snapshot)
    return user


@transaction.atomic
def change_password(user, *, current_password: str, new_password: str) -> None:
    user = User.objects.select_for_update().get(pk=user.pk)
    verify_current_password(user, current_password)
    user.set_password(new_password)
    user.save(update_fields=["password"])
    audit_row = audit_services.log(user, "password.changed", "User", user.pk, None, None)
    revoke_all_tokens(user)
    _best_effort_enqueue_password_changed(user, audit_log_id=audit_row.pk)


@transaction.atomic
def request_email_change(user, *, new_email: str, password: str) -> None:
    user = User.objects.select_for_update().get(pk=user.pk)
    verify_current_password(user, password)
    previous_pending = user.pending_email or None
    user.pending_email = new_email
    user.save(update_fields=["pending_email"])
    enqueue_email_change(user)
    audit_services.log(
        user,
        "email_change.requested",
        "User",
        user.pk,
        {"email": user.email, "pending_email": previous_pending},
        {"pending_email": new_email},
    )
    from core.notify import notify

    notify(
        user,
        "email_changed",
        "Confirm your new email",
        f"We sent a link to {new_email}. Your old address keeps working until then.",
        link="/app/profile",
    )


def _load_email_change_token_strict(token: str) -> dict:
    """Parse an email-change signed token; map expiry to a distinct error code."""
    from django.core import signing

    try:
        return load_email_change_token(token)
    except signing.SignatureExpired:
        raise ValidationFailed(
            "This verification link has expired.",
            code="expired_token",
        ) from None
    except Exception:
        raise ValidationFailed(
            "Invalid or expired verification link.",
            code="invalid_token",
        ) from None


def _complete_email_change_locked(user: User, token_email: str) -> User:
    user = User.objects.select_for_update().get(pk=user.pk)
    if not user.is_active:
        raise Forbidden(
            "This account is not active.",
            code="account_inactive",
        )

    if user.email == token_email and not user.pending_email:
        return user

    pending = (user.pending_email or "").strip().lower()
    if not pending or pending != token_email:
        raise ValidationFailed(
            "This verification link is no longer valid.",
            code="email_change_stale",
        )

    if User.objects.filter(email__iexact=token_email).exclude(pk=user.pk).exists():
        raise ConflictError(
            "That email address is already in use.",
            code="email_taken",
            fields={"new_email": ["That email address is already in use."]},
        )

    old_email = user.email
    user.email = token_email
    user.pending_email = ""
    user.email_verified = True
    user.save(update_fields=["email", "pending_email", "email_verified"])
    audit_row = audit_services.log(
        user,
        "email_change.verified",
        "User",
        user.pk,
        {"email": old_email},
        {"email": user.email},
    )
    revoke_all_tokens(user)
    _best_effort_enqueue_email_change_completion(
        user,
        audit_log_id=audit_row.pk,
        previous_email=old_email,
        new_email=user.email,
    )
    from core.notify import notify

    notify(
        user,
        "email_changed",
        "Your email was changed",
        f"You now sign in with {user.email}.",
        link="/app/profile",
    )
    return user


@transaction.atomic
def verify_email_change_for_token(token: str) -> User:
    """Complete a pending email change using only the signed link token (no session)."""
    payload = _load_email_change_token_strict(token)
    token_email = (payload.get("email") or "").lower()
    user_id = payload.get("user_id")
    if not token_email or not user_id:
        raise ValidationFailed("Invalid or expired verification link.", code="invalid_token")

    user = User.objects.filter(pk=user_id).first()
    if user is None:
        raise ValidationFailed("Invalid or expired verification link.", code="invalid_token")
    return _complete_email_change_locked(user, token_email)


@transaction.atomic
def verify_email_change(user, token: str) -> User:
    payload = _load_email_change_token_strict(token)
    token_email = (payload.get("email") or "").lower()
    if payload.get("user_id") != user.pk:
        raise ValidationFailed("Invalid or expired verification link.", code="invalid_token")
    return _complete_email_change_locked(user, token_email)


@transaction.atomic
def cancel_email_change(user) -> None:
    user = User.objects.select_for_update().get(pk=user.pk)
    if not user.pending_email:
        return
    pending = user.pending_email
    cancel_pending_email_change_deliveries(user.pk)
    user.pending_email = ""
    user.save(update_fields=["pending_email"])
    audit_services.log(
        user,
        "email_change.cancelled",
        "User",
        user.pk,
        {"pending_email": pending},
        {"pending_email": None},
    )


def _tombstone_email(user_id: int) -> str:
    token = secrets.token_hex(8)
    return f"closed.{user_id}.{token}@{ACCOUNT_TOMBSTONE_DOMAIN}".lower()


@transaction.atomic
def close_account(user, *, password: str) -> None:
    """Deactivate and anonymise the user, preserving financial FK history by primary key."""
    user = User.objects.select_for_update().get(pk=user.pk)
    if not user.is_active:
        raise ConflictError(
            "This account is already closed.",
            code="account_already_closed",
        )
    verify_current_password(user, password)
    account_selectors.assert_account_closure_allowed(user)

    cancel_pending_verification_deliveries(user.pk)
    cancel_pending_email_change_deliveries(user.pk)
    cancel_pending_reminder_deliveries_for_user(user.pk)
    cancel_pending_account_notification_deliveries(user.pk)

    tombstone = _tombstone_email(user.pk)
    for _ in range(8):
        if not User.objects.filter(email__iexact=tombstone).exclude(pk=user.pk).exists():
            break
        tombstone = _tombstone_email(user.pk)
    else:
        raise ConflictError(
            "Could not close this account right now. Try again.",
            code="tombstone_collision",
        )

    old_snapshot = {"is_active": True, "name": user.name}
    user.is_active = False
    user.email = tombstone
    user.name = CLOSED_ACCOUNT_DISPLAY_NAME
    user.pending_email = ""
    user.email_reminders = False
    user.set_unusable_password()
    user.save(
        update_fields=[
            "is_active",
            "email",
            "name",
            "pending_email",
            "email_reminders",
            "password",
        ]
    )
    revoke_all_tokens(user)
    audit_services.log(
        user,
        "account.closed",
        "User",
        user.pk,
        old_snapshot,
        {"is_active": False, "name": CLOSED_ACCOUNT_DISPLAY_NAME},
        summary="Account closed",
    )
