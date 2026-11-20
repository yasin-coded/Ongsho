import pytest
from corsheaders.conf import conf
from django.conf import settings
from django.test import Client


GOOD_ORIGIN = "http://localhost:5173"
EVIL_ORIGIN = "http://evil.example"


@pytest.fixture(autouse=True)
def cors_env(settings):
    settings.FRONTEND_ORIGINS = "http://localhost:5173"


def _preflight(origin: str):
    client = Client()
    return client.options(
        "/api/auth/refresh/",
        HTTP_ORIGIN=origin,
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="x-requested-with",
    )


@pytest.mark.django_db
def test_allowed_origin_preflight():
    response = _preflight(GOOD_ORIGIN)
    assert response["Access-Control-Allow-Origin"] == GOOD_ORIGIN
    assert response["Access-Control-Allow-Credentials"] == "true"
    headers = response.get("Access-Control-Allow-Headers", "").lower()
    assert "x-requested-with" in headers
    assert response.get("Access-Control-Allow-Origin") != "*"


@pytest.mark.django_db
def test_disallowed_origin_preflight():
    response = _preflight(EVIL_ORIGIN)
    assert "Access-Control-Allow-Origin" not in response


@pytest.mark.django_db
def test_normal_response_includes_cors_headers():
    client = Client()
    response = client.get("/api/categories/", HTTP_ORIGIN=GOOD_ORIGIN)
    assert response["Access-Control-Allow-Origin"] == GOOD_ORIGIN
    assert response.get("Access-Control-Allow-Origin") != "*"


def test_default_allow_headers_include_required():
    configured = {h.lower() for h in conf.CORS_ALLOW_HEADERS}
    assert "authorization" in configured
    assert "content-type" in configured
    assert "x-requested-with" in configured


def test_cors_applies_to_api_only(settings):
    assert settings.CORS_URLS_REGEX == r"^/api/.*$"
    client = Client()
    response = client.get("/admin/", HTTP_ORIGIN=GOOD_ORIGIN)
    assert "Access-Control-Allow-Origin" not in response
