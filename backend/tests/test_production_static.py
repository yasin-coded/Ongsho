"""Production static files (WhiteNoise + collectstatic)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.test import Client, override_settings


def test_static_url_and_root_configured():
    assert settings.STATIC_URL == "/static/"
    assert settings.STATIC_ROOT == settings.BASE_DIR / "staticfiles"


def test_whitenoise_middleware_order():
    middleware = settings.MIDDLEWARE
    sec = middleware.index("django.middleware.security.SecurityMiddleware")
    wn = middleware.index("whitenoise.middleware.WhiteNoiseMiddleware")
    assert wn == sec + 1


def test_staticfiles_storage_uses_whitenoise_manifest():
    backend = settings.STORAGES["staticfiles"]["BACKEND"]
    assert backend == "whitenoise.storage.CompressedManifestStaticFilesStorage"


def test_default_storage_unchanged():
    assert settings.STORAGES["default"]["BACKEND"] == "django.core.files.storage.FileSystemStorage"


@pytest.fixture()
def collected_static(tmp_path):
    static_root = tmp_path / "collected"
    with override_settings(STATIC_ROOT=static_root, DEBUG=False):
        call_command("collectstatic", verbosity=0, interactive=False, clear=True)
    return static_root


def test_collectstatic_includes_admin_css_and_manifest(collected_static: Path):
    manifest_path = collected_static / "staticfiles.json"
    assert manifest_path.is_file(), "collectstatic should emit staticfiles.json for manifest storage"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "paths" in manifest
    assert "admin/css/base.css" in manifest["paths"]

    admin_css = list(collected_static.glob("admin/css/base*.css"))
    assert admin_css, "admin base stylesheet should exist under admin/css/"


@override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"])
def test_serve_collected_admin_css(collected_static):
    with override_settings(STATIC_ROOT=collected_static):
        client = Client()
        response = client.get("/static/admin/css/base.css")
        assert response.status_code == 200
        assert "text/css" in (response.get("Content-Type") or "")
        body = b"".join(response.streaming_content).decode("utf-8", errors="replace")
        assert "django" in body.lower() or "admin" in body.lower()


@override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"])
def test_serve_collected_admin_js(collected_static):
    with override_settings(STATIC_ROOT=collected_static):
        client = Client()
        response = client.get("/static/admin/js/theme.js")
        assert response.status_code == 200
        assert "javascript" in (response.get("Content-Type") or "")