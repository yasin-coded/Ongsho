from __future__ import annotations

import re
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from core.email_backends.brevo import BrevoEmailError, _NETWORK_ERRORS
from core.outbox.errors import OutboxDeliveryError, OutboxRetryableError

# Seconds between attempts (8 steps; final step used for attempt 8+).
BACKOFF_SCHEDULE_SECONDS = (60, 300, 900, 3600, 7200, 14400, 28800, 43200)

_HTTP_STATUS_RE = re.compile(r"HTTP (\d{3})")


def next_backoff_at(attempt_count: int, *, retry_after_seconds: int | None = None) -> timezone.datetime:
    """attempt_count is 1-based count after a failed attempt."""
    idx = min(max(attempt_count, 1), len(BACKOFF_SCHEDULE_SECONDS)) - 1
    delay = BACKOFF_SCHEDULE_SECONDS[idx]
    if retry_after_seconds is not None:
        delay = max(delay, retry_after_seconds)
    return timezone.now() + timedelta(seconds=delay)


def classify_send_exception(exc: BaseException) -> OutboxDeliveryError:
    if isinstance(exc, OutboxDeliveryError):
        return exc
    if isinstance(exc, BrevoEmailError):
        msg = str(exc)
        if "not configured" in msg.lower():
            return OutboxDeliveryError("config_missing", permanent=True)
        match = _HTTP_STATUS_RE.search(msg)
        if match:
            status = int(match.group(1))
            return classify_http_status(status)
        if "invalid" in msg.lower():
            return OutboxDeliveryError("invalid_message", permanent=True)
        return OutboxRetryableError("provider_error")
    if isinstance(exc, _NETWORK_ERRORS):
        return OutboxRetryableError("network_error")
    if isinstance(exc, ValueError):
        return OutboxDeliveryError("invalid_message", permanent=True)
    return OutboxRetryableError("unknown_error")


def classify_http_status(status: int, *, retry_after_seconds: int | None = None) -> OutboxDeliveryError:
    if status == 429:
        return OutboxRetryableError("rate_limited", retry_after_seconds=retry_after_seconds)
    if 500 <= status <= 599:
        return OutboxRetryableError("provider_5xx")
    if 400 <= status < 500:
        return OutboxDeliveryError(f"provider_{status}", permanent=True)
    if status in (201, 202):
        raise ValueError("success status passed to classifier")
    return OutboxRetryableError("provider_error")