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

from accounts.constants import DEFAULT_AVATAR_ID
from accounts.emails import send_password_reset_email, send_verification_email
from accounts.tokens import load_email_verification_token
from core.exceptions import Forbidden, Unauthorized, ValidationFailed

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
