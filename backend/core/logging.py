from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Any

_REQUEST_ID_ATTR = "_ongsho_request_id"

_EMAIL_RE = re.compile(
    r"\b([a-zA-Z0-9._%+-])[a-zA-Z0-9._%+-]*@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b"
)
_JWT_RE = re.compile(r"\beyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b")
_LONG_B64_RE = re.compile(r"\b[A-Za-z0-9+/]{32,}={0,2}\b")
_INVITE_PATH_RE = re.compile(r"(/api/invites/)[^/\s?]+", re.IGNORECASE)
_TXN_RE = re.compile(r"\b(txn_[a-zA-Z0-9]{8,}|transaction[_-]?id[=:\s]+[a-zA-Z0-9]{8,})\b", re.IGNORECASE)


def mask_sensitive_text(text: str) -> str:
    if not text:
        return text
    out = _EMAIL_RE.sub(r"\1***@\2", text)
    out = _JWT_RE.sub("eyJ***", out)
    out = _INVITE_PATH_RE.sub(r"\1***", out)
    out = _TXN_RE.sub("txn_***", out)
    out = _LONG_B64_RE.sub("***", out)
    return out


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask_sensitive_text(str(record.msg))
        if record.args:
            record.args = tuple(
                mask_sensitive_text(str(arg)) if isinstance(arg, str) else arg for arg in record.args
            )
        return True


class RequestLogMiddleware:
    """Assign X-Request-ID and log one summary line per request (no headers/body)."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger("ongsho.request")

    def __call__(self, request):
        request_id = str(uuid.uuid4())
        setattr(request, _REQUEST_ID_ATTR, request_id)
        start = time.perf_counter()
        response = self.get_response(request)
        duration_ms = int((time.perf_counter() - start) * 1000)
        response["X-Request-ID"] = request_id

        user_id = "-"
        if hasattr(request, "user") and request.user.is_authenticated:
            user_id = str(request.user.pk)

        route = "-"
        if getattr(request, "resolver_match", None):
            route = request.resolver_match.url_name or request.resolver_match.view_name or route

        self.logger.info(
            "request_id=%s user_id=%s route=%s method=%s status=%s duration_ms=%s",
            request_id,
            user_id,
            route,
            request.method,
            response.status_code,
            duration_ms,
        )
        return response


def request_id(request) -> str | None:
    return getattr(request, _REQUEST_ID_ATTR, None)