"""API response security headers (production hardening)."""

from __future__ import annotations

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

_API_PREFIX = "/api/"
_CACHE_HEADER = "Cache-Control"
_DEFAULT_CACHE = "no-store"
_CSP = "default-src 'none'; frame-ancestors 'none'"
_REFERRER = "no-referrer"
_NOSNIFF = "nosniff"
_PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=()"


def _admin_prefix() -> str:
    url = getattr(settings, "ADMIN_URL", "admin/")
    if not url.startswith("/"):
        url = f"/{url}"
    return url


class ApiSecurityHeadersMiddleware(MiddlewareMixin):
    """Attach security headers to JSON/API responses; skip Django admin."""

    def process_response(self, request, response):
        path = request.path
        if not path.startswith(_API_PREFIX):
            return response
        if path.startswith(_admin_prefix()):
            return response

        if _CACHE_HEADER not in response:
            response[_CACHE_HEADER] = _DEFAULT_CACHE
        response["Content-Security-Policy"] = _CSP
        response["Referrer-Policy"] = _REFERRER
        response["X-Content-Type-Options"] = _NOSNIFF
        response["Permissions-Policy"] = _PERMISSIONS_POLICY
        return response