from __future__ import annotations

import hashlib

from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle


def client_ip(request) -> str:
    """Client IP from REMOTE_ADDR, or X-Forwarded-For when NUM_PROXIES > 0."""
    num_proxies = int(getattr(settings, "NUM_PROXIES", 0) or 0)
    if num_proxies > 0:
        xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if xff:
            parts = [part.strip() for part in xff.split(",") if part.strip()]
            idx = len(parts) - num_proxies
            if idx >= 0:
                return parts[idx]
    return request.META.get("REMOTE_ADDR", "") or ""


def hash_email(email: str) -> str:
    return hashlib.sha256(email.lower().strip().encode("utf-8")).hexdigest()


def parse_ongsho_rate(rate: str) -> tuple[int, int]:
    """Parse rates like 10/m, 10/h, 10/15m into (max_requests, window_seconds)."""
    num_s, period_s = rate.split("/", 1)
    num = int(num_s)
    if period_s == "s":
        return num, 1
    if period_s == "m":
        return num, 60
    if period_s == "h":
        return num, 3600
    if period_s == "d":
        return num, 86400
    if period_s.endswith("m") and period_s[:-1].isdigit():
        return num, int(period_s[:-1]) * 60
    if period_s.endswith("h") and period_s[:-1].isdigit():
        return num, int(period_s[:-1]) * 3600
    if period_s.endswith("s") and period_s[:-1].isdigit():
        return num, int(period_s[:-1])
    raise ValueError(f"Unsupported throttle rate: {rate!r}")


class OngshoRateThrottle(SimpleRateThrottle):
    """Cache-backed throttle with rates from settings.THROTTLE_RATES."""

    scope: str | None = None

    def parse_rate(self, rate):
        if rate is None:
            return None, None
        return parse_ongsho_rate(rate)

    def get_rate(self):
        if not self.scope:
            return None
        return settings.THROTTLE_RATES.get(self.scope)

    def get_cache_key(self, request, view):
        if self.rate is None:
            return None
        ident = self.get_ident(request)
        if ident is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": ident}


class IpRateThrottle(OngshoRateThrottle):
    def get_ident(self, request):
        return client_ip(request)


class EmailRateThrottle(OngshoRateThrottle):
    email_field = "email"

    def get_ident(self, request):
        if not hasattr(request, "data"):
            return None
        raw = request.data.get(self.email_field) or ""
        if not raw:
            return None
        return hash_email(str(raw))

class UserRateThrottle(OngshoRateThrottle):
    def get_ident(self, request):
        if request.user and request.user.is_authenticated:
            return str(request.user.pk)
        return None


class PostOnlyMixin:
    def allow_request(self, request, view):
        if request.method != "POST":
            return True
        return super().allow_request(request, view)


# --- Auth & account (IP / email) ---


class LoginIpThrottle(IpRateThrottle):
    scope = "login_ip"


class LoginEmailThrottle(EmailRateThrottle):
    scope = "login_email"


class RegisterIpThrottle(IpRateThrottle):
    scope = "register_ip"


class PasswordResetRequestIpThrottle(IpRateThrottle):
    scope = "password_reset_request_ip"


class PasswordResetRequestEmailThrottle(EmailRateThrottle):
    scope = "password_reset_request_email"


class PasswordResetConfirmIpThrottle(IpRateThrottle):
    scope = "password_reset_confirm_ip"


class VerifyEmailIpThrottle(IpRateThrottle):
    scope = "verify_email_ip"


class ResendVerificationIpThrottle(IpRateThrottle):
    scope = "resend_verification_ip"


class ResendVerificationEmailThrottle(EmailRateThrottle):
    scope = "resend_verification_email"


class RefreshIpThrottle(IpRateThrottle):
    scope = "refresh_ip"


# --- Sharing / invites ---


class PublicInviteGetIpThrottle(IpRateThrottle):
    scope = "public_invite_get_ip"


class PlanJoinGetIpThrottle(IpRateThrottle):
    scope = "plan_join_get_ip"


class PlanJoinSignupIpThrottle(IpRateThrottle):
    scope = "plan_join_signup_ip"


class InviteSignupIpThrottle(IpRateThrottle):
    scope = "invite_signup_ip"


class InviteCreateUserThrottle(PostOnlyMixin, UserRateThrottle):
    scope = "invite_create_user"


class InviteReplaceUserThrottle(UserRateThrottle):
    scope = "invite_replace_user"


# --- Payments & statements ---


class PaymentSubmitUserThrottle(UserRateThrottle):
    scope = "payment_submit_user"


class StatementDownloadUserThrottle(UserRateThrottle):
    scope = "statement_download_user"