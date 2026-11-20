"""
Outbound payload value checks — block sensitive delivery artifacts in JSON, not ordinary content.
"""

from __future__ import annotations

import re
from typing import Any

_DELIVERY_URL_RE = re.compile(
    r"https?://[^\s]+/(?:invite/[A-Za-z0-9_-]{16,}|verify-email\?[^\s]*token=|reset-password\?[^\s]*token=)",
    re.IGNORECASE,
)
_CREDENTIAL_RE = re.compile(
    r"(?:\bxkeysib-[A-Za-z0-9_-]{10,}\b|"
    r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b|"
    r"\b[A-Za-z0-9_-]{43}=\b)",
)


def _iter_string_values(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_string_values(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_string_values(item)


def assert_payload_value_safety(
    payload: dict[str, Any],
    *,
    invite_delivery_secret: str | None = None,
) -> None:
    """Raise OutboxPayloadError when a value looks like a secret or delivery URL."""
    from core.mail_enqueue import OutboxPayloadError

    if invite_delivery_secret:
        for text in _iter_string_values(payload):
            if invite_delivery_secret in text:
                raise OutboxPayloadError(
                    "Forbidden invite delivery secret in outbox payload value"
                )

    for text in _iter_string_values(payload):
        if _DELIVERY_URL_RE.search(text):
            raise OutboxPayloadError("Forbidden delivery URL in outbox payload value")
        if _CREDENTIAL_RE.search(text):
            raise OutboxPayloadError("Forbidden credential or key material in outbox payload value")