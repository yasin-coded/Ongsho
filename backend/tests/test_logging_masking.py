import logging
from io import StringIO

import pytest
from django.test import RequestFactory
from rest_framework.test import APIClient

from core.logging import RequestLogMiddleware, SensitiveDataFilter, mask_sensitive_text

pytestmark = pytest.mark.django_db


def test_mask_email_jwt_invite_path_and_txn():
    raw = (
        "user secret@example.com failed with eyJhbGciOiJIUzI1NiJ9.payload.sig "
        "at /api/invites/super-secret-token and txn_abc12345678"
    )
    masked = mask_sensitive_text(raw)
    assert "secret@example.com" not in masked
    assert "super-secret-token" not in masked
    assert "eyJhbGciOiJIUzI1NiJ9" not in masked
    assert "abc12345678" not in masked


def test_sensitive_filter_on_handler():
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(SensitiveDataFilter())
    logger = logging.getLogger("test.mask")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    logger.info("mail to alice@gmail.com")
    assert "alice@gmail.com" not in stream.getvalue()
    assert "@gmail.com" in stream.getvalue()


def test_request_middleware_request_id_and_log_fields():
    captured = []

    class _CaptureHandler(logging.Handler):
        def emit(self, record):
            captured.append(self.format(record))

    logger = logging.getLogger("ongsho.request")
    old_handlers = logger.handlers[:]
    handler = _CaptureHandler()
    logger.handlers = [handler]
    logger.propagate = False

    def get_response(request):
        from django.http import HttpResponse

        return HttpResponse("ok", status=200)

    middleware = RequestLogMiddleware(get_response)
    rf = RequestFactory()
    request = rf.get("/api/me/")
    request.user = type("U", (), {"is_authenticated": False})()
    request.resolver_match = type("M", (), {"url_name": "me", "view_name": "me-view"})()
    response = middleware(request)
    assert response["X-Request-ID"]
    assert captured
    line = captured[-1]
    assert "request_id=" in line
    assert "user_id=-" in line
    assert "route=me" in line
    assert "method=GET" in line
    assert "status=200" in line
    assert "duration_ms=" in line
    logger.handlers = old_handlers


@pytest.mark.django_db
def test_request_id_header_on_api():
    client = APIClient()
    r = client.get("/api/auth/login/")
    assert r.status_code in (405, 401, 400)
    assert r.headers.get("X-Request-ID")