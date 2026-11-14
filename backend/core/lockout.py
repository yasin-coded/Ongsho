from __future__ import annotations

import hashlib
import time

from django.core.cache import cache

from core.exceptions import Locked
from core.throttles import hash_email

LOGIN_INVALID_MESSAGE = "The email or password is incorrect."

# Pair: 5 failures / 15 min -> lock 15 min
LOGIN_PAIR_FAIL_LIMIT = 5
LOGIN_PAIR_WINDOW = 15 * 60
LOGIN_PAIR_LOCK = 15 * 60

# Email: 20 failures / 30 min -> lock 30 min
LOGIN_EMAIL_FAIL_LIMIT = 20
LOGIN_EMAIL_WINDOW = 30 * 60
LOGIN_EMAIL_LOCK = 30 * 60

PASSWORD_CONFIRM_FAIL_LIMIT = 5
PASSWORD_CONFIRM_WINDOW = 15 * 60
PASSWORD_CONFIRM_LOCK = 15 * 60

_PAIR_FAIL = "lockout:login:pair:fail:"
_PAIR_LOCK = "lockout:login:pair:lock:"
_EMAIL_FAIL = "lockout:login:email:fail:"
_EMAIL_LOCK = "lockout:login:email:lock:"
_PW_FAIL = "lockout:pwconfirm:fail:"
_PW_LOCK = "lockout:pwconfirm:lock:"


def _now() -> float:
    return time.time()


def _retry_after(expires_at: float | None, default: int) -> int:
    if expires_at is None:
        return default
    return max(1, int(expires_at - _now()))


def _read_lock(key: str) -> float | None:
    val = cache.get(key)
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, dict) and "expires" in val:
        return float(val["expires"])
    return None


def _set_lock(key: str, ttl: int) -> None:
    cache.set(key, {"expires": _now() + ttl}, timeout=ttl)


def _incr_window(key: str, window: int) -> int:
    try:
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window)
        return 1


def _pair_keys(email: str, ip: str) -> tuple[str, str, str]:
    digest = hash_email(email)
    return f"{_PAIR_FAIL}{digest}:{ip}", f"{_PAIR_LOCK}{digest}:{ip}", digest


def assert_login_allowed(*, email: str, ip: str) -> None:
    _, pair_lock_key, digest = _pair_keys(email, ip)
    email_lock_key = f"{_EMAIL_LOCK}{digest}"

    pair_exp = _read_lock(pair_lock_key)
    if pair_exp is not None:
        raise Locked(
            LOGIN_INVALID_MESSAGE,
            retry_after=_retry_after(pair_exp, LOGIN_PAIR_LOCK),
        )

    email_exp = _read_lock(email_lock_key)
    if email_exp is not None:
        raise Locked(
            LOGIN_INVALID_MESSAGE,
            retry_after=_retry_after(email_exp, LOGIN_EMAIL_LOCK),
        )


def record_login_failure(*, email: str, ip: str) -> None:
    fail_key, pair_lock_key, digest = _pair_keys(email, ip)
    email_fail_key = f"{_EMAIL_FAIL}{digest}"
    email_lock_key = f"{_EMAIL_LOCK}{digest}"

    pair_count = _incr_window(fail_key, LOGIN_PAIR_WINDOW)
    if pair_count >= LOGIN_PAIR_FAIL_LIMIT:
        _set_lock(pair_lock_key, LOGIN_PAIR_LOCK)

    email_count = _incr_window(email_fail_key, LOGIN_EMAIL_WINDOW)
    if email_count >= LOGIN_EMAIL_FAIL_LIMIT:
        _set_lock(email_lock_key, LOGIN_EMAIL_LOCK)


def clear_login_success(*, email: str, ip: str) -> None:
    fail_key, pair_lock_key, digest = _pair_keys(email, ip)
    email_fail_key = f"{_EMAIL_FAIL}{digest}"
    email_lock_key = f"{_EMAIL_LOCK}{digest}"
    cache.delete(fail_key)
    cache.delete(pair_lock_key)
    cache.delete(email_fail_key)
    cache.delete(email_lock_key)


def _pw_keys(user_id: int) -> tuple[str, str]:
    ident = hashlib.sha256(str(user_id).encode()).hexdigest()
    return f"{_PW_FAIL}{ident}", f"{_PW_LOCK}{ident}"


PASSWORD_CONFIRM_LOCKED_MESSAGE = "Too many password attempts. Try again later."


def assert_password_confirm_allowed(user_id: int) -> None:
    _, lock_key = _pw_keys(user_id)
    expires = _read_lock(lock_key)
    if expires is not None:
        raise Locked(
            PASSWORD_CONFIRM_LOCKED_MESSAGE,
            retry_after=_retry_after(expires, PASSWORD_CONFIRM_LOCK),
        )


def record_password_confirm_failure(user_id: int) -> None:
    fail_key, lock_key = _pw_keys(user_id)
    count = _incr_window(fail_key, PASSWORD_CONFIRM_WINDOW)
    if count >= PASSWORD_CONFIRM_FAIL_LIMIT:
        _set_lock(lock_key, PASSWORD_CONFIRM_LOCK)


def clear_password_confirm_success(user_id: int) -> None:
    fail_key, lock_key = _pw_keys(user_id)
    cache.delete(fail_key)
    cache.delete(lock_key)