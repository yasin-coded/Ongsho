from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts import services as account_services
from accounts.models import User
from core.mail_enqueue import OutboxEnqueueError
from core.models.outbound_email import OutboundEmail, OutboundEmailStatus, OutboundEmailType
from core.outbox.claim import claim_batch
from core.outbox.dispatch import dispatch_outbound_email
from core.outbox.worker import process_claimed_row
from core.crypto.invite_delivery import decrypt_invite_delivery_secret
from sharing import services as sharing_services
from sharing.models import InviteStatus
from sharing.tokens import hash_invite_token
from tests.outbox_helpers import run_pending_on_commit_hooks


@pytest.fixture(autouse=True)
def _clear_resend_caches():
    cache.clear()
    yield
    cache.clear()


def test_register_creates_user_and_outbox_atomically(db):
    with patch("accounts.emails.send_verification_email") as send_mock:
        user = account_services.register_user(
            email="reg@example.com",
            password="pass12345",
            name="Reg",
        )
        send_mock.assert_not_called()
    row = OutboundEmail.objects.get(user=user, email_type=OutboundEmailType.ACCOUNT_VERIFY)
    assert row.to_email == user.email
    assert "token" not in row.payload


def test_register_rollback_removes_user_and_outbox(db):
    with patch("accounts.services.enqueue_account_verify", side_effect=OutboxEnqueueError("boom")):
        with pytest.raises(OutboxEnqueueError):
            account_services.register_user(
                email="roll@example.com",
                password="pass12345",
                name="Roll",
            )
    assert not User.objects.filter(email="roll@example.com").exists()
    assert OutboundEmail.objects.count() == 0


def test_resend_verification_enqueues_without_sync_send(db):
    user = User.objects.create_user(email="resend@example.com", password="pass12345", name="R", email_verified=False)
    with patch("accounts.emails.send_verification_email") as send_mock:
        account_services.resend_verification("resend@example.com")
        send_mock.assert_not_called()
    assert OutboundEmail.objects.filter(user=user, email_type=OutboundEmailType.VERIFY_RESEND).exists()


@pytest.mark.django_db(transaction=False)
def test_resend_cooldown_blocks_second_enqueue(db):
    user = User.objects.create_user(email="cd@example.com", password="pass12345", name="C", email_verified=False)
    account_services.resend_verification("cd@example.com")
    run_pending_on_commit_hooks()
    account_services.resend_verification("cd@example.com")
    assert OutboundEmail.objects.filter(user=user, email_type=OutboundEmailType.VERIFY_RESEND).count() == 1


def test_resend_enqueue_failure_does_not_set_cooldown(db):
    user = User.objects.create_user(email="fail@example.com", password="pass12345", name="F", email_verified=False)
    with patch("accounts.services.enqueue_verify_resend", side_effect=OutboxEnqueueError("x")):
        with pytest.raises(OutboxEnqueueError):
            account_services.resend_verification("fail@example.com")
    cache_key = account_services._resend_verification_cache_key("fail@example.com")
    assert cache.get(cache_key) is None


@pytest.mark.django_db(transaction=False)
def test_resend_verification_cooldown_registered_on_commit_not_before(db):
    """Cooldown is deferred until the outermost transaction commits (on_commit)."""
    User.objects.create_user(email="commit@example.com", password="pass12345", name="C", email_verified=False)
    cache_key = account_services._resend_verification_cache_key("commit@example.com")
    with transaction.atomic():
        account_services.resend_verification("commit@example.com")
        assert cache.get(cache_key) is None
    run_pending_on_commit_hooks()
    assert cache.get(cache_key) is True


@pytest.mark.django_db(transaction=False)
def test_resend_verification_cooldown_skipped_when_transaction_rolls_back(db):
    User.objects.create_user(email="rollback@example.com", password="pass12345", name="R", email_verified=False)
    cache_key = account_services._resend_verification_cache_key("rollback@example.com")
    with transaction.atomic():
        account_services.resend_verification("rollback@example.com")
        transaction.set_rollback(True)
    assert cache.get(cache_key) is None
    assert not OutboundEmail.objects.filter(email_type=OutboundEmailType.VERIFY_RESEND).exists()


@pytest.mark.django_db(transaction=False)
def test_email_change_resend_cooldown_registered_on_commit(db):
    user = User.objects.create_user(email="ec@example.com", password="pass12345", name="U", email_verified=True)
    user.pending_email = "next@example.com"
    user.save(update_fields=["pending_email"])
    cache_key = account_services._resend_email_change_cache_key(user.pk)
    with transaction.atomic():
        account_services.resend_pending_email_change(user)
        assert cache.get(cache_key) is None
    run_pending_on_commit_hooks()
    assert cache.get(cache_key) is True


def test_email_change_resend_enqueue_failure_does_not_set_cooldown(db):
    user = User.objects.create_user(email="ecf@example.com", password="pass12345", name="U", email_verified=True)
    user.pending_email = "nope@example.com"
    user.save(update_fields=["pending_email"])
    cache_key = account_services._resend_email_change_cache_key(user.pk)
    with patch("accounts.services.enqueue_email_change", side_effect=OutboxEnqueueError("x")):
        with pytest.raises(OutboxEnqueueError):
            account_services.resend_pending_email_change(user)
    assert cache.get(cache_key) is None


def test_password_reset_unknown_still_generic_no_outbox(db):
    with patch("accounts.emails.send_password_reset_email") as send_mock:
        account_services.request_password_reset("nobody@example.com")
        send_mock.assert_not_called()
    assert OutboundEmail.objects.filter(email_type=OutboundEmailType.PASSWORD_RESET).count() == 0


def test_password_reset_known_enqueues_no_sync(db):
    user = User.objects.create_user(
        email="reset@example.com",
        password="pass12345",
        name="R",
        email_verified=True,
    )
    with patch("accounts.emails.send_password_reset_email") as send_mock:
        account_services.request_password_reset("reset@example.com")
        send_mock.assert_not_called()
    row = OutboundEmail.objects.get(user=user, email_type=OutboundEmailType.PASSWORD_RESET)
    assert row.payload == {}


def test_password_reset_token_minted_at_dispatch(db):
    user = User.objects.create_user(
        email="disp@example.com",
        password="pass12345",
        name="D",
        email_verified=True,
    )
    account_services.request_password_reset("disp@example.com")
    row = OutboundEmail.objects.get(user=user)
    token = claim_batch(batch_size=1, worker_id="w")[0][1]
    with patch("accounts.emails.send_password_reset_email") as send_mock:
        process_claimed_row(row_id=row.id, claim_token=token)
        send_mock.assert_called_once()
        _, uid, reset_token = send_mock.call_args[0]
        assert uid and reset_token


def test_email_change_atomic_pending_and_outbox(db):
    user = User.objects.create_user(email="old@example.com", password="pass12345", name="U", email_verified=True)
    with patch("accounts.emails.send_email_change_verification") as send_mock:
        account_services.request_email_change(user, new_email="new@example.com", password="pass12345")
        send_mock.assert_not_called()
    user.refresh_from_db()
    row = OutboundEmail.objects.get(user=user, email_type=OutboundEmailType.EMAIL_CHANGE)
    assert row.to_email == "new@example.com"
    assert user.pending_email == "new@example.com"


@pytest.mark.django_db(transaction=False)
def test_email_change_resend_respects_cooldown(db):
    user = User.objects.create_user(email="p@example.com", password="pass12345", name="U", email_verified=True)
    user.pending_email = "next@example.com"
    user.save(update_fields=["pending_email"])
    account_services.resend_pending_email_change(user)
    run_pending_on_commit_hooks()
    account_services.resend_pending_email_change(user)
    assert OutboundEmail.objects.filter(user=user, email_type=OutboundEmailType.EMAIL_CHANGE).count() == 1


def test_invite_create_enqueues_encrypted_no_json_token(db, world):
    from core.dates import today_dhaka

    with patch("sharing.emails.send_invite_email") as send_mock:
        invite, raw = sharing_services.create_invite(
            world["owner"],
            world["plan_x"].pk,
            email="invitee-new@example.com",
            today=today_dhaka(),
        )
        send_mock.assert_not_called()
    row = OutboundEmail.objects.get(invite=invite, email_type=OutboundEmailType.PLAN_INVITE)
    assert row.delivery_ciphertext
    plain = decrypt_invite_delivery_secret(row.delivery_ciphertext, version=row.delivery_key_version)
    assert hash_invite_token(plain) == invite.token_hash
    assert raw == plain
    assert raw not in str(row.payload)


def test_invite_rotation_cancels_obsolete_delivery(db, world):
    from core.dates import today_dhaka

    owner = world["owner"]
    plan_id = world["plan_x"].pk
    invite, _ = sharing_services.create_invite(
        owner,
        plan_id,
        email="rotate@example.com",
        today=today_dhaka(),
    )
    first = OutboundEmail.objects.get(invite=invite)
    invite2, raw2 = sharing_services.new_invite_link(owner, invite.pk, today=today_dhaka())
    first.refresh_from_db()
    assert first.status == OutboundEmailStatus.CANCELLED
    second = OutboundEmail.objects.get(invite=invite2, status=OutboundEmailStatus.PENDING)
    plain = decrypt_invite_delivery_secret(second.delivery_ciphertext, version=second.delivery_key_version)
    assert hash_invite_token(plain) == invite2.token_hash
    token = claim_batch(batch_size=1, worker_id="w")[0][1]
    with patch("sharing.emails.send_invite_email") as send_mock:
        assert process_claimed_row(row_id=second.id, claim_token=token) == "sent"
        send_mock.assert_called_once()
        assert raw2 in send_mock.call_args.kwargs["invite_link"] or raw2 in str(send_mock.call_args)


def test_invite_stale_dispatch_cancelled(db, world):
    from core.dates import today_dhaka

    owner = world["owner"]
    invite, raw = sharing_services.create_invite(
        owner,
        world["plan_x"].pk,
        email="stale2@example.com",
        today=today_dhaka(),
    )
    row = OutboundEmail.objects.get(invite=invite)
    sharing_services.new_invite_link(owner, invite.pk, today=today_dhaka())
    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.CANCELLED


def test_invite_create_rollback(db, world):
    from core.dates import today_dhaka

    unique = f"rollback-{uuid.uuid4().hex[:8]}@example.com"
    with patch("sharing.services.enqueue_plan_invite_delivery", side_effect=OutboxEnqueueError("fail")):
        with pytest.raises(OutboxEnqueueError):
            sharing_services.create_invite(
                world["owner"],
                world["plan_x"].pk,
                email=unique,
                today=today_dhaka(),
            )
    from sharing.models import Invite

    assert not Invite.objects.filter(email=unique).exists()
    assert OutboundEmail.objects.count() == 0


def test_replace_member_invite_enqueues(db, world):
    from core.dates import today_dhaka

    owner = world["owner"]
    member = world["member_row"]
    with patch("sharing.emails.send_invite_email") as send_mock:
        invite, _ = sharing_services.replace_member(owner, member.pk, email="replace@example.com", today=today_dhaka())
        send_mock.assert_not_called()
    assert OutboundEmail.objects.filter(invite=invite, email_type=OutboundEmailType.PLAN_INVITE).exists()