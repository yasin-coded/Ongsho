"""Integration checks for core.logging.RequestLogMiddleware."""

from __future__ import annotations

import logging
import re

import pytest

from core.logging import SensitiveDataFilter, mask_sensitive_text
from tests.test_auth import APP_HEADER
from tests.test_subscriptions import client_for

LOG_LINE_RE = re.compile(
    r"^request_id=[0-9a-f-]{36} user_id=\S+ route=\S+ method=\w+ status=\d{3} duration_ms=\d+$"
)
FORBIDDEN_IN_LOG = re.compile(
    r"(Cookie|Authorization|password=|\?|query|eyJ[a-zA-Z0-9_-]+\.)",
    re.IGNORECASE,
)


@pytest.mark.django_db
def test_request_log_one_line_and_request_id_header(world, caplog):
    caplog.set_level(logging.INFO, logger="ongsho.request")
    client = client_for(world["owner"])
    r = client.get("/api/me/", **APP_HEADER)
    assert r.status_code == 200
    request_id = r.headers.get("X-Request-ID") or r.get("X-Request-ID")
    assert request_id
    assert len(request_id) == 36

    lines = [rec.getMessage() for rec in caplog.records if rec.name == "ongsho.request"]
    matching = [line for line in lines if request_id in line]
    assert len(matching) == 1, f"expected one log line for request, got {matching!r}"
    line = matching[0]
    assert LOG_LINE_RE.match(line), line
    assert not FORBIDDEN_IN_LOG.search(line)

    client.get(
        "/api/me/?email=leak@example.com&password=secret",
        **APP_HEADER,
        HTTP_COOKIE="session=abc",
        HTTP_AUTHORIZATION="Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.body.sig",
    )
    for rec in caplog.records:
        if rec.name != "ongsho.request":
            continue
        msg = rec.getMessage()
        assert "leak@example.com" not in msg
        assert "password=secret" not in msg
        assert "Cookie" not in msg
        assert "Authorization" not in msg
        assert "eyJhbGci" not in msg


def test_mask_sensitive_text_masks_common_leaks():
    raw = (
        "user bob@test.com txn_ABC12345678 eyJhbGciOiJIUzI1NiJ9.a.b "
        "sk_test_abcdefghij /api/invites/secret-token-here"
    )
    masked = mask_sensitive_text(raw)
    assert "bob@test.com" not in masked
    assert "eyJhbGci" not in masked
    assert "secret-token-here" not in masked
    filt = SensitiveDataFilter()
    rec = logging.LogRecord("x", logging.INFO, "", 0, raw, (), None)
    assert filt.filter(rec)
    assert "bob@test.com" not in rec.msg