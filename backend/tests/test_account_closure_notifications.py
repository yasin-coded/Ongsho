"""Account closure cancels Stage 4 security/payment notification outbox rows."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from django.db import transaction
from django.utils import timezone

from accounts import services as account_services
from audit.models import AuditLog
from core.exceptions import ConflictError
from core.mail_enqueue import enqueue_outbound_email
from core.models.outbound_email import OutboundEmail, OutboundEmailStatus, OutboundEmailType
from core.outbox.claim import claim_batch
from core.outbox.worker import process_claimed_row
from notifications.models import Reminder, ReminderChannel, ReminderKind

from tests.test_account_closure import STRONG_PASSWORD, make_verified


STAGE4_TYPES = (
    OutboundEmailType.EMAIL_CHANGED_NEW,
    OutboundEmailType.EMAIL_CHANGED_PREVIOUS,
    OutboundEmailType.PASSWORD_CHANGED,
    OutboundEmailType.PASSWORD_RESET_COMPLETED,
    OutboundEmailType.PAYMENT_REJECTED,
)


def _minimal_payload(email_type: str) -> dict:
    base = {
        "event": email_type,
        "user_id": 1,
        "audit_log_id": 1,
        "occurred_at": timezone.now().isoformat(),
        "link_path": "/app/profile",
    }
    if email_type in (
        OutboundEmailType.EMAIL_CHANGED_NEW,
        OutboundEmailType.EMAIL_CHANGED_PREVIOUS,
    ):
        base["previous_email"] = "old@example.com"
        base["new_email"] = "new@example.com"
    if email_type == OutboundEmailType.PAYMENT_REJECTED:
        base.update(
            {
                "payment_id": 1,
                "plan_name": "Plan",
                "amount_display": "৳10",
                "method_label": "Bkash",
                "rejection_reason": "test",
                "reviewer_name": "Owner",
                "reviewed_at": timezone.now().isoformat(),
                "payer_first_name": "Pat",
            }
        )
    return base


def _enqueue_stage4_row(user, email_type):
    with transaction.atomic():
        return enqueue_outbound_email(
            email_type=email_type,
            business_event_id=f"closure-test:{email_type}:{user.pk}:{uuid.uuid4()}",
            to_email=user.email if email_type != OutboundEmailType.EMAIL_CHANGED_PREVIOUS else "old@example.com",
            user=user,
            payload=_minimal_payload(email_type),
        )


def _claim_token_for(row_id):
    for rid, token in claim_batch(batch_size=50, worker_id="pytest-closure"):
        if rid == row_id:
            return token
    raise AssertionError(f"row {row_id} not claimed")


@pytest.mark.django_db
@pytest.mark.parametrize("email_type", STAGE4_TYPES)
def test_close_cancels_pending_stage4_type(email_type):
    user = make_verified(f"cls-{email_type}@example.com")
    row = _enqueue_stage4_row(user, email_type)
    account_services.close_account(user, password=STRONG_PASSWORD)
    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.CANCELLED
    assert row.last_error_code == "account_closed"


@pytest.mark.django_db
def test_close_cancels_retry_stage4_rows():
    user = make_verified("cls-retry@example.com")
    rows = [_enqueue_stage4_row(user, t) for t in STAGE4_TYPES]
    for row in rows:
        row.status = OutboundEmailStatus.RETRY
        row.save(update_fields=["status"])
    account_services.close_account(user, password=STRONG_PASSWORD)
    for row in rows:
        row.refresh_from_db()
        assert row.status == OutboundEmailStatus.CANCELLED
        assert row.last_error_code == "account_closed"


@pytest.mark.django_db
def test_close_leaves_sent_stage4_unchanged():
    user = make_verified("cls-sent@example.com")
    row = _enqueue_stage4_row(user, OutboundEmailType.PASSWORD_CHANGED)
    row.status = OutboundEmailStatus.SENT
    row.save(update_fields=["status"])
    account_services.close_account(user, password=STRONG_PASSWORD)
    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.SENT


@pytest.mark.django_db
def test_close_stage4_only_touches_closing_user():
    user = make_verified("cls-self@example.com")
    other = make_verified("cls-other@example.com")
    user_row = _enqueue_stage4_row(user, OutboundEmailType.PASSWORD_CHANGED)
    other_row = _enqueue_stage4_row(other, OutboundEmailType.PASSWORD_CHANGED)
    account_services.close_account(user, password=STRONG_PASSWORD)
    user_row.refresh_from_db()
    other_row.refresh_from_db()
    assert user_row.status == OutboundEmailStatus.CANCELLED
    assert other_row.status == OutboundEmailStatus.PENDING


@pytest.mark.django_db
def test_close_preserves_existing_verification_and_reminder_cancellation(world):
    user = world["outsider"]
    user.email_reminders = True
    user.save(update_fields=["email_reminders"])
    with transaction.atomic():
        verify = enqueue_outbound_email(
            email_type=OutboundEmailType.ACCOUNT_VERIFY,
            business_event_id=f"verify-cls:{user.pk}",
            to_email=user.email,
            user=user,
        )
        email_change = enqueue_outbound_email(
            email_type=OutboundEmailType.EMAIL_CHANGE,
            business_event_id=f"ec-cls:{user.pk}",
            to_email="pending@example.com",
            user=user,
        )
        user.pending_email = "pending@example.com"
        user.save(update_fields=["pending_email"])
        reminder = Reminder.objects.create(
            subscription=world["plan_x"],
            user=user,
            kind=ReminderKind.DUE_SOON,
            target_date=timezone.now().date(),
            days_before=3,
            channel=ReminderChannel.EMAIL,
        )
        rem_row = enqueue_outbound_email(
            email_type=OutboundEmailType.REMINDER,
            business_event_id=f"rem:{reminder.pk}",
            to_email=user.email,
            user=user,
            reminder=reminder,
            payload={"title": "T", "message": "M", "link_path": "/x"},
        )
        stage4 = _enqueue_stage4_row(user, OutboundEmailType.PAYMENT_REJECTED)

    account_services.close_account(user, password=STRONG_PASSWORD)
    for row in (verify, email_change, rem_row, stage4):
        row.refresh_from_db()
        assert row.status == OutboundEmailStatus.CANCELLED
    assert verify.last_error_code == "superseded"
    assert email_change.last_error_code == "superseded"
    assert rem_row.last_error_code == "opt_out"
    assert stage4.last_error_code == "account_closed"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "email_type,send_patch",
    [
        (OutboundEmailType.PASSWORD_CHANGED, "accounts.emails.send_password_changed_notice_email"),
        (OutboundEmailType.PASSWORD_RESET_COMPLETED, "accounts.emails.send_password_reset_completed_notice_email"),
        (OutboundEmailType.EMAIL_CHANGED_NEW, "accounts.emails.send_email_changed_new_notice_email"),
        (OutboundEmailType.EMAIL_CHANGED_PREVIOUS, "accounts.emails.send_email_changed_previous_notice_email"),
        (OutboundEmailType.PAYMENT_REJECTED, "payments.emails.send_payment_rejected_email"),
    ],
)
def test_inactive_user_dispatch_cancelled(email_type, send_patch):
    user = make_verified(f"cls-disp-{email_type}@example.com")
    row = _enqueue_stage4_row(user, email_type)
    claim_token = _claim_token_for(row.pk)
    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.PROCESSING
    account_services.close_account(user, password=STRONG_PASSWORD)
    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.PROCESSING
    with patch(send_patch) as send_mock:
        outcome = process_claimed_row(row_id=row.pk, claim_token=claim_token)
    assert outcome == "cancelled"
    row.refresh_from_db()
    assert row.last_error_code == "user_inactive"
    send_mock.assert_not_called()


@pytest.mark.django_db
def test_closure_blocker_leaves_stage4_rows_pending(world):
    user = world["member"]
    row = _enqueue_stage4_row(user, OutboundEmailType.PASSWORD_CHANGED)
    with pytest.raises(ConflictError):
        account_services.close_account(user, password=STRONG_PASSWORD)
    row.refresh_from_db()
    assert row.status == OutboundEmailStatus.PENDING
    user.refresh_from_db()
    assert user.is_active is True


@pytest.mark.django_db
def test_financial_audit_unchanged_after_closure_with_stage4_rows(world):
    from tests.test_account_closure import make_closable_owner

    owner = make_closable_owner(world)
    original_pk = owner.pk
    from payments.models import Payment
    from dues.models import Due

    payment_ids = list(Payment.objects.filter(recorded_by=owner).values_list("pk", flat=True))
    due_ids = list(Due.objects.filter(member__user=owner).values_list("pk", flat=True))
    audit_before = AuditLog.objects.filter(user_id=original_pk).count()
    _enqueue_stage4_row(owner, OutboundEmailType.PAYMENT_REJECTED)
    account_services.close_account(owner, password=STRONG_PASSWORD)
    assert Payment.objects.filter(pk__in=payment_ids, recorded_by_id=original_pk).count() == len(payment_ids)
    assert Due.objects.filter(pk__in=due_ids).count() == len(due_ids)
    assert AuditLog.objects.filter(user_id=original_pk).count() >= audit_before + 1