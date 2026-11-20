"""Django email backend for Brevo transactional API (POST /v3/smtp/email)."""

from __future__ import annotations

import base64
import json
import logging
import socket
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage as StdEmailMessage
from email.utils import getaddresses, parseaddr

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import EmailMessage, EmailMultiAlternatives

logger = logging.getLogger(__name__)

BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"

# Injected in tests via unittest.mock.patch("core.email_backends.brevo.urlopen", ...).
urlopen = urllib.request.urlopen

_NETWORK_ERRORS = (
    urllib.error.URLError,
    socket.timeout,
    TimeoutError,
    ssl.SSLError,
    ConnectionError,
    BrokenPipeError,
)


class BrevoEmailError(Exception):
    """Brevo send failed; message must never contain API keys or email bodies."""


def _parse_name_email(raw: str) -> dict[str, str]:
    name, email = parseaddr(raw or "")
    email = (email or "").strip()
    if not email:
        raise ValueError("Invalid email address.")
    out: dict[str, str] = {"email": email}
    if name:
        out["name"] = name[:70]
    return out


def _recipient_list(addresses: list[str]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for name, email in getaddresses(addresses):
        email = (email or "").strip()
        if not email:
            continue
        entry: dict[str, str] = {"email": email}
        if name:
            entry["name"] = name[:70]
        items.append(entry)
    return items


def _html_body(message: EmailMessage) -> str | None:
    """First text/html alternative, or body when content_subtype is html."""
    if isinstance(message, EmailMultiAlternatives):
        for content, mimetype in message.alternatives:
            if mimetype == "text/html":
                return content
        return None
    if getattr(message, "content_subtype", "plain") == "html":
        return message.body
    return None


def _plain_body(message: EmailMessage, *, html: str | None) -> str | None:
    """Plain-text body for Brevo; never duplicate HTML markup as text."""
    if not message.body:
        return None
    if getattr(message, "content_subtype", "plain") == "html":
        return None
    if html and isinstance(message, EmailMultiAlternatives):
        return message.body
    if html and not isinstance(message, EmailMultiAlternatives):
        return None
    return message.body


def _encode_attachment_content(filename: str, content) -> dict[str, str]:
    name = str(filename or "").strip()
    if not name:
        raise ValueError("Attachment filename is required.")
    if isinstance(content, str):
        payload = content.encode("utf-8")
    elif isinstance(content, (bytes, bytearray)):
        payload = bytes(content)
    else:
        raise ValueError(f"Attachment {name!r} must be bytes or text.")
    if not payload:
        raise ValueError(f"Attachment {name!r} is empty.")
    return {
        "name": name,
        "content": base64.b64encode(payload).decode("ascii"),
    }


def _attachments(message: EmailMessage) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for part in message.attachments or []:
        if isinstance(part, StdEmailMessage):
            filename = part.get_filename() or "attachment"
            payload = part.get_payload(decode=True)
            if payload is None:
                raise ValueError(f"Attachment {filename!r} has no decodable content.")
            out.append(_encode_attachment_content(filename, payload))
            continue
        if isinstance(part, str):
            raise ValueError(
                "File-path attachments are not supported by the Brevo backend; "
                "attach content as (filename, bytes, mimetype)."
            )
        if isinstance(part, (tuple, list)):
            if len(part) == 1:
                raise ValueError(
                    "File-path attachments are not supported by the Brevo backend; "
                    "attach content as (filename, bytes, mimetype)."
                )
            if len(part) < 2:
                raise ValueError("Attachment tuple must include filename and content.")
            filename, content, *_rest = part
            out.append(_encode_attachment_content(filename, content))
            continue
        raise ValueError(f"Unsupported attachment type: {type(part).__name__}")
    return out


def build_brevo_payload(message: EmailMessage) -> dict:
    """Map a Django EmailMessage to a Brevo transactional JSON body."""
    from_email = message.from_email or settings.DEFAULT_FROM_EMAIL
    sender = _parse_name_email(from_email)

    to_list = _recipient_list(message.to or [])
    if not to_list:
        raise ValueError("No recipients.")

    payload: dict = {
        "sender": sender,
        "to": to_list,
        "subject": message.subject or "",
    }

    html = _html_body(message)
    plain = _plain_body(message, html=html)
    if html:
        payload["htmlContent"] = html
    if plain:
        payload["textContent"] = plain
    if not html and not plain:
        raise ValueError("Email has no text or HTML body.")

    cc = _recipient_list(message.cc or [])
    if cc:
        payload["cc"] = cc
    bcc = _recipient_list(message.bcc or [])
    if bcc:
        payload["bcc"] = bcc

    if message.reply_to:
        reply_addrs = _recipient_list(message.reply_to)
        if reply_addrs:
            # Brevo accepts a single replyTo object; additional addresses are ignored.
            payload["replyTo"] = reply_addrs[0]

    attachments = _attachments(message)
    if attachments:
        payload["attachment"] = attachments

    return payload


class BrevoEmailBackend(BaseEmailBackend):
    """Send mail through Brevo's transactional API."""

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = (getattr(settings, "BREVO_API_KEY", None) or "").strip()
        self.timeout = float(getattr(settings, "BREVO_API_TIMEOUT", 10))

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        sent = 0
        for message in email_messages:
            if self._send_one(message):
                sent += 1
        return sent

    def _send_one(self, message: EmailMessage) -> bool:
        if not self.api_key:
            if not self.fail_silently:
                raise BrevoEmailError("Brevo API key is not configured.")
            logger.warning("brevo_email_skipped reason=missing_api_key")
            return False

        try:
            payload = build_brevo_payload(message)
        except ValueError as exc:
            if not self.fail_silently:
                raise BrevoEmailError(str(exc)) from exc
            logger.warning("brevo_email_skipped reason=invalid_message")
            return False

        try:
            status = self._post_json(payload)
        except BrevoEmailError:
            if not self.fail_silently:
                raise
            logger.warning("brevo_email_failed reason=brevo_error")
            return False
        except _NETWORK_ERRORS as exc:
            if not self.fail_silently:
                raise BrevoEmailError("Brevo request failed.") from exc
            logger.warning(
                "brevo_email_failed",
                extra={"reason": type(exc).__name__},
            )
            return False

        if status not in (201, 202):
            if not self.fail_silently:
                raise BrevoEmailError(f"Brevo returned HTTP {status}.")
            logger.warning("brevo_email_failed", extra={"status": status})
            return False
        return True

    def _post_json(self, payload: dict) -> int:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            BREVO_SEND_URL,
            data=data,
            method="POST",
            headers={
                "accept": "application/json",
                "content-type": "application/json",
                "api-key": self.api_key,
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return int(response.status)
        except urllib.error.HTTPError as exc:
            # Do not read/decode body into exceptions (may echo sensitive content).
            return int(exc.code)