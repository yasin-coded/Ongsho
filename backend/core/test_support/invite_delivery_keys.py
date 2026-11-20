"""
Test-only invite delivery encryption keys. Never use in production.

Loaded by the pytest bootstrap (see `backend/conftest.py`). Keys are deterministic and public.
"""

from __future__ import annotations

import os

# Valid Fernet test material (two versions for rotation/versioning tests).
TEST_INVITE_DELIVERY_ENCRYPTION_KEYS_JSON = (
    '{"1": "xFEfHMLkadBG8Sb0XCV-VDjwNEjtw6z2kf0MuFdhyhg=", '
    '"2": "Qh7g_BUmq38bXW-on_RTmP2-SbX1q6xNo108PyfyD50="}'
)


def apply_test_invite_delivery_encryption_env() -> None:
    os.environ.setdefault("INVITE_DELIVERY_ENCRYPTION_KEYS", TEST_INVITE_DELIVERY_ENCRYPTION_KEYS_JSON)
    os.environ.setdefault("INVITE_DELIVERY_ENCRYPTION_ACTIVE_VERSION", "1")
    os.environ.setdefault("OUTBOX_LEASE_SECONDS", "900")