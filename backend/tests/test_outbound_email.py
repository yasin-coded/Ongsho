from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from django.db import IntegrityError, connections, transaction
from django.test import override_settings

from accounts.models import User
from core.crypto.invite_delivery import (
    InviteDeliveryCryptoError,
    InviteDeliveryDecryptError,
    clear_invite_delivery_crypto_cache,
    decrypt_invite_delivery_secret,
    encrypt_invite_delivery_secret,
    parse_invite_delivery_encryption_keys_json,
)
from config.settings import _load_invite_delivery_encryption_active_version
from core.mail_enqueue import (
    OutboxEnqueueError,
    OutboxPayloadError,
    OutboxTransactionRequired,
    assert_in_outbox_transaction,
    enqueue_outbound_email,
)
from core.models.outbound_email import OutboundEmail, OutboundEmailStatus, OutboundEmailType
from sharing.models import Invite, InviteStatus
from sharing.tokens import new_invite_token


KEYS_V1_V2 = {
    1: "xFEfHMLkadBG8Sb0XCV-VDjwNEjtw6z2kf0MuFdhyhg=",
    2: "Qh7g_BUmq38bXW-on_RTmP2-SbX1q6xNo108PyfyD50=",
}


@pytest.fixture(autouse=True)
def _invite_crypto_settings(settings):
    settings.INVITE_DELIVERY_ENCRYPTION_KEYS = KEYS_V1_V2
    settings.INVITE_DELIVERY_ENCRYPTION_ACTIVE_VERSION = 1
    clear_invite_delivery_crypto_cache()
    yield
    clear_invite_delivery_crypto_cache()


def test_parse_invite_delivery_encryption_keys_json_accepts_versions():
    parsed = parse_invite_delivery_encryption_keys_json(
        '{"1": "xFEfHMLkadBG8Sb0XCV-VDjwNEjtw6z2kf0MuFdhyhg=", '
        '"2": "Qh7g_BUmq38bXW-on_RTmP2-SbX1q6xNo108PyfyD50="}'
    )
    assert parsed[1] and parsed[2]


def test_parse_rejects_invalid_fernet_material():
    with pytest.raises(RuntimeError, match="not valid Fernet"):
        parse_invite_delivery_encryption_keys_json('{"1": "not-a-fernet-key"}')


def test_encrypt_decrypt_round_trip_active_version():
    ciphertext, version = encrypt_invite_delivery_secret("raw-invite-token-value")
    assert version == 1
    assert decrypt_invite_delivery_secret(ciphertext, version=version) == "raw-invite-token-value"


@override_settings(INVITE_DELIVERY_ENCRYPTION_ACTIVE_VERSION=2)
def test_encrypt_uses_active_version_and_old_ciphertext_still_decrypts():
    clear_invite_delivery_crypto_cache()
    old_ciphertext, old_version = encrypt_invite_delivery_secret("v1-era-token")
    assert old_version == 2
    assert decrypt_invite_delivery_secret(old_ciphertext, version=old_version) == "v1-era-token"


def test_decrypt_wrong_version_fails():
    ciphertext, version = encrypt_invite_delivery_secret("secret")
    with override_settings(INVITE_DELIVERY_ENCRYPTION_KEYS={2: KEYS_V1_V2[2]}):
        clear_invite_delivery_crypto_cache()
        with pytest.raises(InviteDeliveryCryptoError):
            decrypt_invite_delivery_secret(ciphertext, version=version)


def test_missing_key_version_raises():
    with override_settings(INVITE_DELIVERY_ENCRYPTION_KEYS={2: KEYS_V1_V2[2]}, INVITE_DELIVERY_ENCRYPTION_ACTIVE_VERSION=1):
        clear_invite_delivery_crypto_cache()
        with pytest.raises(InviteDeliveryCryptoError, match="Unknown invite delivery encryption key version"):
            encrypt_invite_delivery_secret("x")


def test_active_version_must_exist_in_key_map(monkeypatch):
    monkeypatch.setenv("INVITE_DELIVERY_ENCRYPTION_ACTIVE_VERSION", "2")
    with pytest.raises(RuntimeError, match="not present in INVITE_DELIVERY_ENCRYPTION_KEYS"):
        _load_invite_delivery_encryption_active_version({1: KEYS_V1_V2[1]})


def test_enqueue_requires_atomic_block(db):
    user = User.objects.create_user(email="a@example.com", password="pass12345", name="A")
    db_conn = connections["default"]
    with patch.object(db_conn, "in_atomic_block", False):
        with pytest.raises(OutboxTransactionRequired):
            enqueue_outbound_email(
                email_type=OutboundEmailType.ACCOUNT_VERIFY,
                business_event_id=f"user:register:{user.pk}",
                to_email=user.email,
                user=user,
            )


def test_enqueue_rollback_does_not_persist(db):
    user = User.objects.create_user(email="rollback@example.com", password="pass12345", name="R")
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            enqueue_outbound_email(
                email_type=OutboundEmailType.ACCOUNT_VERIFY,
                business_event_id=f"user:register:{user.pk}:attempt-1",
                to_email=user.email,
                user=user,
            )
            raise RuntimeError("rollback")
    assert OutboundEmail.objects.count() == 0


def test_business_event_id_unique_constraint(db):
    user = User.objects.create_user(email="dup@example.com", password="pass12345", name="D")
    event_id = f"verify_resend:{uuid.uuid4()}"
    with transaction.atomic():
        enqueue_outbound_email(
            email_type=OutboundEmailType.VERIFY_RESEND,
            business_event_id=event_id,
            to_email=user.email,
            user=user,
        )
    with transaction.atomic():
        with pytest.raises(IntegrityError):
            enqueue_outbound_email(
                email_type=OutboundEmailType.VERIFY_RESEND,
                business_event_id=event_id,
                to_email=user.email,
                user=user,
            )


def test_forbidden_token_fields_in_payload(db):
    user = User.objects.create_user(email="payload@example.com", password="pass12345", name="P")
    with transaction.atomic():
        with pytest.raises(OutboxPayloadError):
            enqueue_outbound_email(
                email_type=OutboundEmailType.PASSWORD_RESET,
                business_event_id=f"reset:{uuid.uuid4()}",
                to_email=user.email,
                user=user,
                payload={"reset_url": "https://example.com/reset"},
            )


def test_forbidden_sensitive_value_in_metadata(db):
    user = User.objects.create_user(email="meta@example.com", password="pass12345", name="M")
    with transaction.atomic():
        with pytest.raises(OutboxPayloadError, match="delivery URL"):
            enqueue_outbound_email(
                email_type=OutboundEmailType.PASSWORD_RESET,
                business_event_id=f"reset:{uuid.uuid4()}",
                to_email=user.email,
                user=user,
                payload={
                    "metadata": {
                        "note": "http://localhost:5173/reset-password?uid=1&token=signed-value-here",
                    },
                },
            )


def test_forbidden_invite_secret_embedded_in_metadata(db, world):
    raw, token_hash = new_invite_token()
    invite = Invite.objects.create(
        shared_plan=world["shared_x"],
        invited_by=world["owner"],
        email="embed@example.com",
        token_hash=token_hash,
        expires_on="2027-01-01T00:00:00Z",
        status=InviteStatus.PENDING,
    )
    with transaction.atomic():
        with pytest.raises(OutboxPayloadError, match="invite delivery secret"):
            enqueue_outbound_email(
                email_type=OutboundEmailType.PLAN_INVITE,
                business_event_id=f"invite:create:{invite.pk}",
                to_email=invite.email,
                invite=invite,
                invite_delivery_secret=raw,
                payload={"metadata": {"copied": raw}},
            )


def test_legitimate_payload_values_allowed(db):
    user = User.objects.create_user(email="ok@example.com", password="pass12345", name="Ok User")
    with transaction.atomic():
        row = enqueue_outbound_email(
            email_type=OutboundEmailType.ACCOUNT_VERIFY,
            business_event_id=f"user:register:{uuid.uuid4()}",
            to_email=user.email,
            user=user,
            payload={"metadata": {"plan_name": "Netflix", "inviter_name": "Sam"}},
        )
    assert row.payload["metadata"]["plan_name"] == "Netflix"


def test_nested_savepoint_rollback_removes_outbox_but_keeps_outer(db):
    user = User.objects.create_user(email="nested@example.com", password="pass12345", name="Nested")
    with transaction.atomic():
        try:
            with transaction.atomic():
                enqueue_outbound_email(
                    email_type=OutboundEmailType.VERIFY_RESEND,
                    business_event_id=f"verify_resend:{uuid.uuid4()}",
                    to_email=user.email,
                    user=user,
                )
                raise RuntimeError("force inner rollback")
        except RuntimeError:
            pass
        assert OutboundEmail.objects.count() == 0
        enqueue_outbound_email(
            email_type=OutboundEmailType.VERIFY_RESEND,
            business_event_id=f"verify_resend:{uuid.uuid4()}",
            to_email=user.email,
            user=user,
        )
    assert OutboundEmail.objects.count() == 1


def test_plan_invite_db_requires_invite_fk(db):
    with transaction.atomic():
        with pytest.raises(IntegrityError):
            OutboundEmail.objects.create(
                business_event_id=f"invite:bad:{uuid.uuid4()}",
                email_type=OutboundEmailType.PLAN_INVITE,
                to_email="x@example.com",
            )


def test_plan_invite_stores_ciphertext_not_in_json(db, world):
    raw, token_hash = new_invite_token()
    invite = Invite.objects.create(
        shared_plan=world["shared_x"],
        invited_by=world["owner"],
        email="invitee@example.com",
        token_hash=token_hash,
        expires_on="2027-01-01T00:00:00Z",
        status=InviteStatus.PENDING,
    )
    with transaction.atomic():
        row = enqueue_outbound_email(
            email_type=OutboundEmailType.PLAN_INVITE,
            business_event_id=f"invite:create:{invite.pk}",
            to_email=invite.email,
            invite=invite,
            invite_delivery_secret=raw,
        )
    assert row.delivery_ciphertext
    assert row.delivery_key_version == 1
    assert "token" not in row.payload
    assert raw not in str(row.payload)
    plain = decrypt_invite_delivery_secret(row.delivery_ciphertext, version=row.delivery_key_version)
    assert plain == raw


def test_one_active_invite_delivery_constraint(db, world):
    raw, token_hash = new_invite_token()
    invite = Invite.objects.create(
        shared_plan=world["shared_x"],
        invited_by=world["owner"],
        email="two@example.com",
        token_hash=token_hash,
        expires_on="2027-01-01T00:00:00Z",
        status=InviteStatus.PENDING,
    )
    with transaction.atomic():
        enqueue_outbound_email(
            email_type=OutboundEmailType.PLAN_INVITE,
            business_event_id=f"invite:create:{invite.pk}",
            to_email=invite.email,
            invite=invite,
            invite_delivery_secret=raw,
        )
    with transaction.atomic():
        with pytest.raises(IntegrityError):
            enqueue_outbound_email(
                email_type=OutboundEmailType.PLAN_INVITE,
                business_event_id=f"invite:resend:{invite.pk}:{uuid.uuid4()}",
                to_email=invite.email,
                invite=invite,
                invite_delivery_secret=raw,
            )


def test_second_invite_outbox_allowed_after_first_sent(db, world):
    raw, token_hash = new_invite_token()
    invite = Invite.objects.create(
        shared_plan=world["shared_x"],
        invited_by=world["owner"],
        email="sent@example.com",
        token_hash=token_hash,
        expires_on="2027-01-01T00:00:00Z",
        status=InviteStatus.PENDING,
    )
    with transaction.atomic():
        first = enqueue_outbound_email(
            email_type=OutboundEmailType.PLAN_INVITE,
            business_event_id=f"invite:create:{invite.pk}",
            to_email=invite.email,
            invite=invite,
            invite_delivery_secret=raw,
        )
    first.status = OutboundEmailStatus.SENT
    first.delivery_ciphertext = None
    first.save(update_fields=["status", "delivery_ciphertext"])
    raw2, _ = new_invite_token()
    with transaction.atomic():
        second = enqueue_outbound_email(
            email_type=OutboundEmailType.PLAN_INVITE,
            business_event_id=f"invite:rotate:{invite.pk}:{uuid.uuid4()}",
            to_email=invite.email,
            invite=invite,
            invite_delivery_secret=raw2,
        )
    assert second.pk != first.pk


def test_plan_invite_missing_secret_raises(db, world):
    raw, token_hash = new_invite_token()
    invite = Invite.objects.create(
        shared_plan=world["shared_x"],
        invited_by=world["owner"],
        email="nos@example.com",
        token_hash=token_hash,
        expires_on="2027-01-01T00:00:00Z",
        status=InviteStatus.PENDING,
    )
    with transaction.atomic():
        with pytest.raises(OutboxEnqueueError):
            enqueue_outbound_email(
                email_type=OutboundEmailType.PLAN_INVITE,
                business_event_id=f"invite:create:{invite.pk}",
                to_email=invite.email,
                invite=invite,
            )


def test_assert_in_outbox_transaction_outside_atomic():
    db_conn = connections["default"]
    with patch.object(db_conn, "in_atomic_block", False):
        with pytest.raises(OutboxTransactionRequired):
            assert_in_outbox_transaction()


def test_settings_outbox_lease_and_max_attempts():
    from django.conf import settings

    assert settings.OUTBOX_LEASE_SECONDS > 0
    assert settings.OUTBOUND_EMAIL_MAX_ATTEMPTS > 0


def test_decrypt_invalid_ciphertext():
    with pytest.raises(InviteDeliveryDecryptError):
        decrypt_invite_delivery_secret(b"not-valid", version=1)