"""
Versioned Fernet encryption for invite delivery secrets (raw invite token at rest).

Key versions: configure INVITE_DELIVERY_ENCRYPTION_KEYS as JSON map of version -> Fernet key.
New ciphertext uses INVITE_DELIVERY_ENCRYPTION_ACTIVE_VERSION. Older ciphertext remains
decryptable with its stored delivery_key_version until rows are sent, cancelled, or re-encrypted.

Encryption settings are immutable for a running process: _fernet_for_version is cached after first
use. Production key or active-version changes require a controlled deploy/restart (no runtime reload).
Tests may call clear_invite_delivery_crypto_cache() after overriding settings.

Invitation rotation race (worker stage, no DB txn during Brevo):
After the worker verifies hash_invite_token(decrypted) == invite.token_hash, another request may
rotate the invite hash before Brevo accepts the HTTP request. The emailed link may then fail
acceptance even though the outbox eventually marks sent. Mitigation: cancel superseded outboxes in
the rotation transaction; accept a narrow stale-link window without holding a DB transaction open
during the provider call.
"""

from __future__ import annotations

import json
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class InviteDeliveryCryptoError(Exception):
    pass


class InviteDeliveryDecryptError(InviteDeliveryCryptoError):
    pass


@lru_cache(maxsize=16)
def _fernet_for_version(version: int) -> Fernet:
    keys: dict[int, str] = settings.INVITE_DELIVERY_ENCRYPTION_KEYS
    material = keys.get(version)
    if not material:
        raise InviteDeliveryCryptoError(f"Unknown invite delivery encryption key version: {version}")
    try:
        return Fernet(material.encode("ascii"))
    except (TypeError, ValueError) as exc:
        raise InviteDeliveryCryptoError("Invalid Fernet key material for invite delivery") from exc


def encrypt_invite_delivery_secret(plaintext: str) -> tuple[bytes, int]:
    """
    Encrypt the raw invite token for storage on OutboundEmail.delivery_ciphertext.
    Never log plaintext or resulting ciphertext.
    """
    if not isinstance(plaintext, str) or not plaintext:
        raise ValueError("Invite delivery plaintext must be a non-empty string")
    version = settings.INVITE_DELIVERY_ENCRYPTION_ACTIVE_VERSION
    token = _fernet_for_version(version).encrypt(plaintext.encode("utf-8"))
    return token, version


def clear_invite_delivery_crypto_cache() -> None:
    _fernet_for_version.cache_clear()


def decrypt_invite_delivery_secret(ciphertext: bytes, *, version: int) -> str:
    """Decrypt a stored invite delivery secret. Never log the result."""
    if not ciphertext:
        raise InviteDeliveryDecryptError("Missing delivery ciphertext")
    try:
        raw = _fernet_for_version(version).decrypt(ciphertext)
    except InvalidToken as exc:
        raise InviteDeliveryDecryptError("Invalid delivery ciphertext") from exc
    return raw.decode("utf-8")


def parse_invite_delivery_encryption_keys_json(raw: str) -> dict[int, str]:
    """Parse and validate versioned Fernet keys from env JSON."""
    if not raw or not raw.strip():
        raise RuntimeError("Missing INVITE_DELIVERY_ENCRYPTION_KEYS")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("INVITE_DELIVERY_ENCRYPTION_KEYS must be valid JSON object") from exc
    if not isinstance(parsed, dict) or not parsed:
        raise RuntimeError("INVITE_DELIVERY_ENCRYPTION_KEYS must be a non-empty JSON object")
    out: dict[int, str] = {}
    for key, value in parsed.items():
        try:
            version = int(key)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("INVITE_DELIVERY_ENCRYPTION_KEYS keys must be integer version strings") from exc
        if version < 1:
            raise RuntimeError("INVITE_DELIVERY_ENCRYPTION_KEYS version must be >= 1")
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"INVITE_DELIVERY_ENCRYPTION_KEYS[{key}] must be a non-empty string")
        try:
            Fernet(value.strip().encode("ascii"))
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"INVITE_DELIVERY_ENCRYPTION_KEYS[{key}] is not valid Fernet material") from exc
        out[version] = value.strip()
    return out