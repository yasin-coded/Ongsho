from __future__ import annotations

import hashlib

from django.contrib.auth import authenticate, get_user_model
from django.core.cache import cache
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken, UntypedToken

from audit import services as audit_services
from accounts.constants import DEFAULT_AVATAR_ID
from accounts.emails import send_email_change_verification, send_password_reset_email, send_verification_email
from accounts.tokens import load_email_change_token, load_email_verification_token
from core.exceptions import ConflictError, Forbidden, Unauthorized, ValidationFailed

User = get_user_model()

PASSWORD_RESET_GENERIC_MESSAGE = (
    "If an account exists with a verified email, you will receive password reset instructions."
)
REGISTER_MESSAGE = "Check your email to verify your account before signing in."
RESEND_VERIFICATION_MESSAGE = (
    "If an account exists and still needs verification, you will receive an email with a new link."
)
RESEND_VERIFICATION_COOLDOWN_SECONDS = 60
_RESEND_VERIFY_CACHE_PREFIX = "accounts:resend-verify:"


def verify_current_password(user, password: str) -> None:
    if not password:
        raise ValidationFailed(
            "Enter your password.",
            code="invalid_password",
            fields={"password": ["Enter your password."]},
        )
    if not user.check_password(password):
        # TODO: increment failed-password lockout counter for this user.
        raise ValidationFailed(
            "The password is not correct.",
            code="invalid_password",
            fields={"password": ["The password is not correct."]},
        )


@transaction.atomic
def register_user(*, email: str, password: str, name: str) -> User:
    if User.objects.filter(email__iexact=email).exists():
        raise ValidationFailed(
            "A user with this email already exists.",
            fields={"email": ["A user with this email already exists."]},
            code="validation_failed",
        )
    user = User.objects.create_user(
        email=email,
        password=password,
        name=name,
        email_verified=False,
        avatar_id=DEFAULT_AVATAR_ID,
    )
    send_verification_email(user)
    return user


def _resend_verification_cache_key(email: str) -> str:
    digest = hashlib.sha256(email.lower().encode("utf-8")).hexdigest()
    return f"{_RESEND_VERIFY_CACHE_PREFIX}{digest}"


def resend_verification(email: str) -> None:
    user = User.objects.filter(email__iexact=email, is_active=True, email_verified=False).first()
    if not user:
        return
    cache_key = _resend_verification_cache_key(email)
    if cache.get(cache_key):
        return
    send_verification_email(user)
    cache.set(cache_key, True, timeout=RESEND_VERIFICATION_COOLDOWN_SECONDS)


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


def login_user(*, email: str, password: str) -> tuple[str, str, User]:
    user = authenticate(username=email, password=password)
    if user is None:
        raise Unauthorized(
            "The email or password is incorrect.",
            code="invalid_credentials",
        )
    if not user.email_verified:
        raise Forbidden(
            "Verify your email before signing in.",
            code="email_not_verified",
        )
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


def request_password_reset(email: str) -> None:
    user = User.objects.filter(email__iexact=email, is_active=True, email_verified=True).first()
    if not user:
        return
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    send_password_reset_email(user, uid, token)


def confirm_password_reset(*, uid: str, token: str, new_password: str) -> None:
    user = _user_from_uid(uid)
    if user is None or not default_token_generator.check_token(user, token):
        raise ValidationFailed("Invalid or expired reset link.", code="invalid_token")

    user.set_password(new_password)
    user.save(update_fields=["password"])
    revoke_all_tokens(user)


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


def resend_pending_email_change(user) -> None:
    if not user.pending_email:
        raise ValidationFailed(
            "No pending email change.",
            code="nothing_pending",
        )
    cache_key = _resend_email_change_cache_key(user.pk)
    if cache.get(cache_key):
        return
    send_email_change_verification(user, user.pending_email)
    cache.set(cache_key, True, timeout=RESEND_EMAIL_CHANGE_COOLDOWN_SECONDS)


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
    if not user.check_password(current_password):
        raise ValidationFailed(
            "The password is not correct.",
            code="invalid_password",
            fields={"password": ["The password is not correct."]},
        )
    user.set_password(new_password)
    user.save(update_fields=["password"])
    audit_services.log(user, "password.changed", "User", user.pk, None, None)
    revoke_all_tokens(user)


@transaction.atomic
def request_email_change(user, *, new_email: str, password: str) -> None:
    user = User.objects.select_for_update().get(pk=user.pk)
    if not user.check_password(password):
        raise ValidationFailed(
            "The password is not correct.",
            code="invalid_password",
            fields={"password": ["The password is not correct."]},
        )
    previous_pending = user.pending_email or None
    user.pending_email = new_email
    user.save(update_fields=["pending_email"])
    send_email_change_verification(user, new_email)
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


@transaction.atomic
def verify_email_change(user, token: str) -> User:
    try:
        payload = load_email_change_token(token)
    except Exception:
        raise ValidationFailed("Invalid or expired verification link.", code="invalid_token")

    token_email = (payload.get("email") or "").lower()
    if payload.get("user_id") != user.pk:
        raise ValidationFailed("Invalid or expired verification link.", code="invalid_token")

    user = User.objects.select_for_update().get(pk=user.pk)
    if user.email == token_email and not user.pending_email:
        return user

    if not user.pending_email or user.pending_email != token_email:
        raise ValidationFailed("Invalid or expired verification link.", code="invalid_token")

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
    audit_services.log(
        user,
        "email_change.verified",
        "User",
        user.pk,
        {"email": old_email},
        {"email": user.email},
    )
    revoke_all_tokens(user)
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
def cancel_email_change(user) -> None:
    user = User.objects.select_for_update().get(pk=user.pk)
    if not user.pending_email:
        return
    pending = user.pending_email
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
