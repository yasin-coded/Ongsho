"""Production settings and deploy checks (hardening Part 1)."""

from __future__ import annotations

import pytest
from django.conf import settings
from django.core.management import call_command
from django.test import override_settings

from config.settings import apply_production_rest_framework

PRODUCTION_OVERRIDES = {
    "DEBUG": False,
    "SECRET_KEY": "test-deploy-check-key-not-used-in-prod",
    "ALLOWED_HOSTS": ["api.example.com"],
    "CSRF_TRUSTED_ORIGINS": ["https://app.example.com"],
    "DEFAULT_FROM_EMAIL": "Ongsho <noreply@example.com>",
    "FRONTEND_BASE_URL": "https://app.example.com",
    "REFRESH_COOKIE_SECURE": True,
    "REFRESH_COOKIE_SAMESITE": "None",
    "SECURE_SSL_REDIRECT": True,
    "TRUST_PROXY_SSL": True,
    "ADMIN_ENABLED": True,
    "ADMIN_URL": "admin/",
    "CORS_ALLOWED_ORIGINS": ["https://app.example.com"],
    "REST_FRAMEWORK": apply_production_rest_framework(
        {
            "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
            "DEFAULT_AUTHENTICATION_CLASSES": [
                "accounts.authentication.ActiveUserJWTAuthentication",
            ],
            "EXCEPTION_HANDLER": "core.exceptions.ongsho_exception_handler",
        },
        debug=False,
    ),
}


@override_settings(**PRODUCTION_OVERRIDES)
def test_deploy_check_clean():
    call_command("check", deploy=True)


def test_production_drfr_json_only():
    from config.settings import _REST_FRAMEWORK_BASE, apply_production_rest_framework

    rf = apply_production_rest_framework(_REST_FRAMEWORK_BASE, debug=False)
    assert rf["DEFAULT_RENDERER_CLASSES"] == ["rest_framework.renderers.JSONRenderer"]
    assert rf["DEFAULT_PARSER_CLASSES"] == ["rest_framework.parsers.JSONParser"]


@override_settings(
    DEBUG=False,
    REFRESH_COOKIE_SECURE=True,
    REFRESH_COOKIE_SAMESITE="None",
    SECURE_SSL_REDIRECT=True,
    SECURE_HSTS_SECONDS=31_536_000,
    SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
    SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True,
    DATA_UPLOAD_MAX_MEMORY_SIZE=1_048_576,
)
def test_production_security_flags():
    from accounts.cookies import REFRESH_COOKIE_PATH, set_refresh_cookie

    assert settings.SECURE_SSL_REDIRECT is True
    assert settings.SECURE_HSTS_SECONDS == 31_536_000
    assert settings.SECURE_HSTS_INCLUDE_SUBDOMAINS is True
    assert settings.SECURE_CONTENT_TYPE_NOSNIFF is True
    assert settings.X_FRAME_OPTIONS == "DENY"
    assert settings.SECURE_REFERRER_POLICY == "same-origin"
    assert settings.SESSION_COOKIE_SECURE is True
    assert settings.CSRF_COOKIE_SECURE is True
    assert settings.DATA_UPLOAD_MAX_MEMORY_SIZE == 1_048_576

    from django.http import HttpResponse

    resp = HttpResponse()
    set_refresh_cookie(resp, "token")
    cookie = resp.cookies["refresh_token"]
    assert cookie["secure"] is True
    assert cookie["httponly"] is True
    assert cookie["samesite"].lower() == "none"
    assert cookie["path"] == REFRESH_COOKIE_PATH