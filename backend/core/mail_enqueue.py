"""
Transactional outbox enqueue helpers.

OutboundEmail rows must be inserted inside the same database transaction as the related
business mutation. Callers must invoke these helpers from within transaction.atomic();
assert_in_outbox_transaction() enforces that contract in every environment (DEBUG or not).

Stage 1: foundation only — domain services still use synchronous send_mail until Stage 2.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import connection, transaction

from core.crypto.invite_delivery import encrypt_invite_delivery_secret
from core.mail_payload import assert_payload_value_safety
from core.models.outbound_email import OutboundEmail, OutboundEmailType
from core.outbox.wake import schedule_outbox_wake_after_commit

_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "token",
        "raw_token",
        "invite_token",
        "invite_url",
        "reset_url",
        "verify_url",
        "url",
        "link",
        "delivery_secret",
    }
)


class OutboxEnqueueError(Exception):
    pass


class OutboxTransactionRequired(OutboxEnqueueError):
    pass


class OutboxPayloadError(OutboxEnqueueError):
    pass


def assert_in_outbox_transaction() -> None:
    if not connection.in_atomic_block:
        raise OutboxTransactionRequired(
            "OutboundEmail must be enqueued inside the caller's active transaction.atomic() block"
        )


def _sanitize_payload(
    payload: dict[str, Any] | None,
    *,
    invite_delivery_secret: str | None = None,
) -> dict[str, Any]:
    data = dict(payload or {})
    for key in data:
        if key.lower() in _FORBIDDEN_PAYLOAD_KEYS:
            raise OutboxPayloadError(f"Forbidden plaintext token/url field in outbox payload: {key}")
    assert_payload_value_safety(data, invite_delivery_secret=invite_delivery_secret)
    return data


def enqueue_outbound_email(
    *,
    email_type: str,
    business_event_id: str,
    to_email: str,
    user=None,
    invite=None,
    reminder=None,
    payload: dict[str, Any] | None = None,
    invite_delivery_secret: str | None = None,
    idempotency_key: uuid.UUID | None = None,
) -> OutboundEmail:
    """
    Insert one OutboundEmail row in the current transaction.

    business_event_id must be unique per accepted business operation (DB unique constraint).
    idempotency_key defaults to a new UUID; both id and idempotency_key are UUIDs.
    """
    assert_in_outbox_transaction()

    if not business_event_id or not business_event_id.strip():
        raise OutboxEnqueueError("business_event_id is required")
    if not to_email or not str(to_email).strip():
        raise OutboxEnqueueError("to_email is required")

    safe_payload = _sanitize_payload(payload, invite_delivery_secret=invite_delivery_secret)

    row = OutboundEmail(
        id=uuid.uuid4(),
        idempotency_key=idempotency_key or uuid.uuid4(),
        business_event_id=business_event_id.strip(),
        email_type=email_type,
        to_email=to_email.strip(),
        user=user,
        invite=invite,
        reminder=reminder,
        payload=safe_payload,
    )

    if email_type == OutboundEmailType.REMINDER:
        if reminder is None:
            raise OutboxEnqueueError("reminder outbox rows require reminder")
    elif email_type == OutboundEmailType.PLAN_INVITE:
        if invite is None:
            raise OutboxEnqueueError("plan_invite outbox rows require invite")
        if not invite_delivery_secret:
            raise OutboxEnqueueError("plan_invite requires invite_delivery_secret (encrypted; not stored in JSON)")
        ciphertext, version = encrypt_invite_delivery_secret(invite_delivery_secret)
        row.delivery_ciphertext = ciphertext
        row.delivery_key_version = version
    elif invite_delivery_secret:
        raise OutboxEnqueueError("invite_delivery_secret is only valid for plan_invite")

    row.save()
    schedule_outbox_wake_after_commit()
    return row


@transaction.atomic
def enqueue_outbound_email_in_transaction(**kwargs) -> OutboundEmail:
    """Testing helper: wrap enqueue in its own atomic block."""
    return enqueue_outbound_email(**kwargs)