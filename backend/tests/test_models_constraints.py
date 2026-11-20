from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from accounts.constants import AVATAR_KEY_SET
from audit.models import AuditLog
from billing.models import Charge, ChargeStatus
from catalog.models import Category, ServiceName
from core.choices import Currency, PaymentMethod
from dues.models import Due, DueStatus
from payments.models import Payment, PaymentAllocation, ReviewStatus
from plans.models import ExchangeRate, PlanMode, Subscription, SubscriptionStatus
from sharing.models import Invite, InviteStatus, OwnershipTransfer, SharedPlan, SplitType, TransferStatus

User = get_user_model()


@pytest.mark.django_db
def test_case_insensitive_email_uniqueness():
    User.objects.create_user(email="Person@Example.com", password="pass12345", name="A")
    with pytest.raises(IntegrityError):
        User.objects.create_user(email="person@example.com", password="pass12345", name="B")


@pytest.mark.django_db
def test_create_superuser_flags():
    user = User.objects.create_superuser(email="admin@example.com", password="pass12345", name="Admin")
    assert user.is_staff and user.is_superuser and user.email_verified


@pytest.mark.django_db
def test_avatar_key_validation():
    user = User.objects.create_user(email="a@example.com", password="pass12345", name="A")
    user.avatar_id = "bad"
    with pytest.raises(ValidationError):
        user.save()
    assert AVATAR_KEY_SET


@pytest.mark.django_db
def test_archived_manager_hides_plans(world):
    from django.utils import timezone

    sub = world["plan_x"]
    Subscription.all_with_archived.filter(pk=sub.pk).update(archived_on=timezone.now())
    assert not Subscription.objects.filter(pk=sub.pk).exists()
    assert Subscription.all_with_archived.filter(pk=sub.pk).exists()


@pytest.mark.django_db
def test_plan_mode_lock(world):
    sub = world["plan_x"]
    sub.plan_mode = PlanMode.RESELLER
    with pytest.raises(ValidationError):
        sub.save()


@pytest.mark.django_db
def test_shared_plan_one_to_one(world):
    with pytest.raises(IntegrityError):
        SharedPlan.objects.create(subscription=world["plan_x"], split_type=SplitType.CUSTOM)


@pytest.mark.django_db
def test_charge_period_unique(world):
    charge = world["due_x"].charge
    with pytest.raises(IntegrityError):
        Charge.objects.create(
            subscription=world["plan_x"],
            period_start=charge.period_start,
            period_end="2026-04-04",
            due_date="2026-03-04",
            amount=Decimal("100.00"),
            currency=Currency.BDT,
            amount_bdt=Decimal("100.00"),
            status=ChargeStatus.DUE,
        )


@pytest.mark.django_db
def test_due_unique_per_member(world):
    with pytest.raises(IntegrityError):
        Due.objects.create(
            charge=world["due_x"].charge,
            member=world["due_x"].member,
            amount_bdt=Decimal("1.00"),
            status=DueStatus.DUE,
        )


@pytest.mark.django_db
def test_amount_must_be_positive(world):
    with pytest.raises(IntegrityError):
        Charge.objects.create(
            subscription=world["plan_x"],
            period_start="2026-05-05",
            period_end="2026-06-04",
            due_date="2026-05-04",
            amount=Decimal("0.00"),
            currency=Currency.BDT,
            amount_bdt=Decimal("0.00"),
            status=ChargeStatus.DUE,
        )


@pytest.mark.django_db
def test_payment_txn_partial_unique_allows_null(world):
    shared = world["shared_x"]
    member = world["due_x"].member
    Payment.objects.create(
        shared_plan=shared,
        member=member,
        recorded_by=world["owner"],
        method=PaymentMethod.BKASH,
        transaction_id=None,
        amount=Decimal("100.00"),
        review_status=ReviewStatus.PENDING,
    )
    Payment.objects.create(
        shared_plan=shared,
        member=member,
        recorded_by=world["owner"],
        method=PaymentMethod.BKASH,
        transaction_id=None,
        amount=Decimal("50.00"),
        review_status=ReviewStatus.PENDING,
    )


@pytest.mark.django_db
def test_payment_txn_unique_when_set(world):
    shared = world["shared_x"]
    member = world["due_x"].member
    Payment.objects.create(
        shared_plan=shared,
        member=member,
        recorded_by=world["owner"],
        method=PaymentMethod.BKASH,
        transaction_id="TXN001",
        amount=Decimal("100.00"),
        review_status=ReviewStatus.PENDING,
    )
    with pytest.raises(IntegrityError):
        Payment.objects.create(
            shared_plan=shared,
            member=member,
            recorded_by=world["owner"],
            method=PaymentMethod.BKASH,
            transaction_id="TXN001",
            amount=Decimal("50.00"),
            review_status=ReviewStatus.REJECTED,
        )


@pytest.mark.django_db
def test_payment_allocation_positive(world):
    payment = Payment.objects.create(
        shared_plan=world["shared_x"],
        member=world["due_x"].member,
        recorded_by=world["owner"],
        method=PaymentMethod.BKASH,
        amount=Decimal("100.00"),
        review_status=ReviewStatus.PENDING,
    )
    with pytest.raises(IntegrityError):
        PaymentAllocation.objects.create(payment=payment, due=world["due_x"], amount_applied=Decimal("0.00"))


@pytest.mark.django_db
def test_audit_log_append_only(world):
    row = AuditLog.objects.create(user=world["owner"], action="test", entity_type="Due", entity_id=1)
    row.action = "changed"
    with pytest.raises(ValidationError):
        row.save()
    with pytest.raises(ValidationError):
        row.delete()


@pytest.mark.django_db
def test_custom_category_rules(world):
    custom = Category.objects.create(user=world["owner"], name=f"Custom-{world['owner'].id}", is_preset=False)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Category.objects.create(user=world["owner"], name=f"Custom-{world['owner'].id}", is_preset=False)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Category.objects.create(user=None, name="Bad preset", is_preset=False)


@pytest.mark.django_db
def test_ownership_transfer_distinct_users(world):
    with pytest.raises(IntegrityError):
        OwnershipTransfer.objects.create(
            shared_plan=world["shared_x"],
            from_user=world["owner"],
            to_user=world["owner"],
            status=TransferStatus.PENDING,
        )


@pytest.mark.django_db
def test_pending_invite_unique_email(world):
    Invite.objects.create(
        shared_plan=world["shared_x"],
        invited_by=world["owner"],
        email="dup@example.com",
        token_hash="hash-a",
        expires_on="2026-12-31T00:00:00Z",
        status=InviteStatus.PENDING,
    )
    with pytest.raises(IntegrityError):
        Invite.objects.create(
            shared_plan=world["shared_x"],
            invited_by=world["owner"],
            email="dup@example.com",
            token_hash="hash-b",
            expires_on="2026-12-31T00:00:00Z",
            status=InviteStatus.PENDING,
        )


@pytest.mark.django_db
def test_shared_plan_seats_range(world):
    from django.db import IntegrityError, transaction
    from sharing.models import SharedPlan

    world["shared_x"].seats = 1
    world["shared_x"].save()
    world["shared_x"].seats = 20
    world["shared_x"].save()
    for bad in (0, 21):
        world["shared_x"].seats = bad
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                world["shared_x"].save()


@pytest.mark.django_db
def test_subscription_new_field_defaults(world):
    sub = world["plan_x"]
    assert sub.billing_from is not None
    assert sub.paused_on is None
    assert sub.cancelled_on is None
    assert sub.created_at is not None


@pytest.mark.django_db
def test_user_reminder_defaults(world):
    user = world["owner"]
    assert user.email_reminders is True
    assert user.reminder_days == "7,1"


@pytest.mark.django_db
def test_audit_log_still_append_only_with_plan_fields(world):
    row = AuditLog.objects.create(
        user=world["owner"],
        action="test",
        entity_type="Subscription",
        entity_id=world["plan_x"].pk,
        plan_id=world["plan_x"].pk,
        summary="Test summary",
    )
    row.summary = "Changed"
    with pytest.raises(ValidationError):
        row.save()
    with pytest.raises(ValidationError):
        row.delete()


@pytest.mark.django_db
def test_exchange_rate_must_be_positive(world):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ExchangeRate.objects.create(
                user=world["owner"],
                rate_date="2026-01-01",
                usd_to_bdt=Decimal("0"),
                source="manual",
            )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ExchangeRate.objects.create(
                user=world["owner"],
                rate_date="2026-01-02",
                usd_to_bdt=Decimal("-1.0000"),
                source="manual",
            )
    row = ExchangeRate.objects.create(
        user=world["owner"],
        rate_date="2026-01-03",
        usd_to_bdt=Decimal("120.5000"),
        source="manual",
    )
    assert row.pk is not None
