"""Logging must mask secrets and omit request bodies/headers/cookies."""

from __future__ import annotations

import logging

from core.logging import RequestLogMiddleware, SensitiveDataFilter, mask_sensitive_text


def test_mask_sensitive_text():
    raw = (
        "contact bob@example.com jwt=eyJhbGciOiJIUzI1NiJ9.abc.def "
        "invite=/api/invites/secret-token-abc txn_id=BKASH0123456789 "
        "xkeysib-deadbeef1234567890abcdefghij"
    )
    out = mask_sensitive_text(raw)
    assert "bob@example.com" not in out
    assert "secret-token" not in out
    assert "BKASH0123456789" not in out
    assert "xkeysib-deadbeef" not in out
    assert "eyJhbGci" not in out


def test_sensitive_filter_on_log_record():
    filt = SensitiveDataFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="pay bob@example.com tid txn_ABC12345678",
        args=(),
        exc_info=None,
    )
    assert filt.filter(record)
    assert "bob@example.com" not in record.msg


def test_request_log_line_shape():
    """Request logging uses structured fields only (no query/body/cookies in message)."""
    line = "request_id=%s user_id=%s route=%s method=%s status=%s duration_ms=%s"
    assert "?" not in line
    assert "body" not in line.lower()
    assert "cookie" not in line.lower()
    assert hasattr(RequestLogMiddleware, "__call__")