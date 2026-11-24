"""Account closure service (stage 1 — no HTTP endpoint)."""

from __future__ import annotations

import pytest
from django.db import transaction
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework.test import APIClient

from accounts import services as account_services
from accounts.cookies import REFRESH_COOKIE_NAME
from accounts.selectors import assert_account_closure_allowed
from audit.models import AuditLog
from core.exceptions import ConflictError, Forbidden, Locked, ValidationFailed
from core.lockout import clear_password_confirm_success
from core.models.outbound_email import OutboundEmail, OutboundEmailStatus, OutboundEmailType
from dues.models import Due
from payments.models import Payment
from plans.models import Subscription
from reports.models import Statement
from sharing.models import Member, MemberStatus

from tests.helpers import run_concurrently
from tests.test_subscriptions import WORLD_PASS, client_for
from tests.test_transfers import ensure_owner_seat, start_transfer
from core.mail_enqueue import enqueue_outbound_email

User = get_user_model()
STRONG_PASSWORD = WORLD_PASS
APP_HEADER = {"HTTP_X_REQUESTED_WITH": "Ongsho"}


def make_verified(email, password=STRONG_PASSWORD, name="User", **extra):
    return User.objects.create_user(
        email=email,
        password=password,
        name=name,
        email_verified=True,
        **extra,
    )


def make_closable_owner(world):
    """Owner with only archived plan_x and no unresolved memberships."""
    owner = world["owner"]
    Member.objects.filter(user=owner, shared_plan__subscription_id=world["plan_y"].pk).update(
        status=MemberStatus.LEFT,
        left_on=world["today"],
    )
    Subscription.objects.filter(pk=world["plan_x"].pk).update(archived_on=timezone.now())
    owner.refresh_from_db()
    return owner


@pytest.mark.django_db
def test_close_wrong_password():
    user = make_verified("pw-wrong@example.com")
    with pytest.raises(ValidationFailed) as exc:
        account_services.close_account(user, password="not-the-password")
    assert exc.value.code == "invalid_password"
    user.refresh_from_db()
    assert user.is_active is True


@pytest.mark.django_db
def test_close_password_confirm_lockout():
    user = make_verified("pw-lock-close@example.com")
    for _ in range(5):
        with pytest.raises(ValidationFailed):
            account_services.verify_current_password(user, "bad-password")
    with pytest.raises(Locked):
        account_services.close_account(user, password=STRONG_PASSWORD)


@pytest.mark.django_db
def test_staff_cannot_close():
    user = make_verified("staff@example.com", is_staff=True)
    with pytest.raises(Forbidden) as exc:
        assert_account_closure_allowed(user)
    assert exc.value.code == "staff_cannot_close"


@pytest.mark.django_db
def test_superuser_cannot_close():
    user = make_verified("su@example.com", is_superuser=True)
    with pytest.raises(Forbidden) as exc:
        assert_account_closure_allowed(user)
    assert exc.value.code == "staff_cannot_close"


@pytest.mark.django_db
def test_blocker_active_owned_subscription(world):
    with pytest.raises(ConflictError) as exc:
        assert_account_closure_allowed(world["owner"])
    assert exc.value.code == "owned_plans_remain"


@pytest.mark.django_db
def test_close_account_service_enforces_owned_plan_blocker(world):
    with pytest.raises(ConflictError) as exc:
        account_services.close_account(world["owner"], password=STRONG_PASSWORD)
    assert exc.value.code == "owned_plans_remain"


@pytest.mark.django_db
def test_archived_owned_does_not_block(world):
    make_closable_owner(world)
    assert_account_closure_allowed(world["owner"])


@pytest.mark.django_db
def test_blocker_pending_transfer_from_user(world):
    ensure_owner_seat(world)
    Member.objects.filter(user=world["owner"], shared_plan=world["shared_y"]).update(
        status=MemberStatus.LEFT,
        left_on=world["today"],
    )
    Subscription.objects.filter(pk=world["plan_y"].pk).update(archived_on=timezone.now())
    target = make_verified("xfer-target@example.com")
    target_member = Member.objects.create(
        shared_plan=world["shared_x"],
        user=target,
        share_type=world["shared_x"].split_type,
        status=MemberStatus.ACTIVE,
        joined_on=world["plan_x"].start_date,
    )
    r = start_transfer(client_for(world["owner"]), world["plan_x"].pk, target_member.pk)
    assert r.status_code == 201, r.content
    with pytest.raises(ConflictError) as exc:
        assert_account_closure_allowed(world["owner"])
    assert exc.value.code == "pending_ownership_transfer"


@pytest.mark.django_db
def test_blocker_pending_transfer_to_user(world):
    ensure_owner_seat(world)
    target = make_verified("xfer-to@example.com")
    target_member = Member.objects.create(
        shared_plan=world["shared_x"],
        user=target,
        share_type=world["shared_x"].split_type,
        status=MemberStatus.ACTIVE,
        joined_on=world["plan_x"].start_date,
    )
    start_transfer(client_for(world["owner"]), world["plan_x"].pk, target_member.pk)
    with pytest.raises(ConflictError) as exc:
        assert_account_closure_allowed(target)
    assert exc.value.code == "pending_ownership_transfer"


@pytest.mark.django_db
def test_blocker_active_membership(world):
    user = make_verified("member-only@example.com")
    Member.objects.create(
        shared_plan=world["shared_x"],
        user=user,
        share_type=world["shared_x"].split_type,
        status=MemberStatus.ACTIVE,
        joined_on=world["plan_x"].start_date,
    )
    with pytest.raises(ConflictError) as exc:
        assert_account_closure_allowed(user)
    assert exc.value.code == "active_membership"


@pytest.mark.django_db
def test_left_membership_does_not_block(world):
    user = make_verified("left-only@example.com")
    Member.objects.create(
        shared_plan=world["shared_x"],
        user=user,
        share_type=world["shared_x"].split_type,
        status=MemberStatus.LEFT,
        joined_on=world["plan_x"].start_date,
        left_on=world["today"],
    )
    assert_account_closure_allowed(user)


@pytest.mark.django_db
def test_close_success_outsider(world):
    user = world["outsider"]
    original_email = user.email
    original_pk = user.pk
    login = APIClient().post(
        "/api/auth/login/",
        {"email": original_email, "password": STRONG_PASSWORD},
        format="json",
    )
    refresh = login.cookies[REFRESH_COOKIE_NAME].value
    from core.mail_outbox import enqueue_account_verify

    enqueue_account_verify(user)
    user.email_reminders = True
    user.pending_email = "pending@example.com"
    user.save(update_fields=["email_reminders", "pending_email"])
    enqueue = OutboundEmail.objects.filter(user=user, email_type=OutboundEmailType.ACCOUNT_VERIFY).first()
    assert enqueue is not None
    with transaction.atomic():
        email_change_row = enqueue_outbound_email(
            email_type=OutboundEmailType.EMAIL_CHANGE,
            business_event_id=f"email_change:test:{user.pk}",
            to_email="pending@example.com",
            user=user,
        )

    account_services.close_account(user, password=STRONG_PASSWORD)
    user = User.objects.get(pk=original_pk)
    assert user.is_active is False
    assert user.email != original_email
    assert user.email.endswith(f"@{account_services.ACCOUNT_TOMBSTONE_DOMAIN}")
    assert user.name == account_services.CLOSED_ACCOUNT_DISPLAY_NAME
    assert user.pending_email == ""
    assert user.email_reminders is False
    assert not user.has_usable_password()
    assert not User.objects.filter(email__iexact=original_email).exists()

    refresh_resp = APIClient().post(
        "/api/auth/refresh/",
        format="json",
        HTTP_COOKIE=f"{REFRESH_COOKIE_NAME}={refresh}",
        **APP_HEADER,
    )
    assert refresh_resp.status_code == 401

    outstanding = OutstandingToken.objects.filter(user_id=original_pk)
    assert outstanding.exists()
    assert outstanding.count() == BlacklistedToken.objects.filter(token__in=outstanding).count()

    assert OutboundEmail.objects.filter(pk=enqueue.pk, status=OutboundEmailStatus.CANCELLED).exists()
    assert OutboundEmail.objects.filter(pk=email_change_row.pk, status=OutboundEmailStatus.CANCELLED).exists()

    audit = AuditLog.objects.get(user_id=original_pk, action="account.closed")
    assert "@" not in str(audit.old_value) + str(audit.new_value)


@pytest.mark.django_db
def test_close_already_closed_raises():
    user = make_verified("twice@example.com")
    account_services.close_account(user, password=STRONG_PASSWORD)
    with pytest.raises(ConflictError) as exc:
        account_services.close_account(user, password=STRONG_PASSWORD)
    assert exc.value.code == "account_already_closed"


@pytest.mark.django_db
def test_reregister_after_closure():
    email = "reuse@example.com"
    user = make_verified(email)
    old_pk = user.pk
    account_services.close_account(user, password=STRONG_PASSWORD)

    new_user = account_services.register_user(email=email, password=STRONG_PASSWORD, name="Fresh")
    assert new_user.pk != old_pk
    assert new_user.is_active is True
    assert new_user.email.lower() == email.lower()

    old = User.objects.get(pk=old_pk)
    assert old.is_active is False
    assert old.email != email.lower()


@pytest.mark.django_db
def test_active_email_still_reserved():
    email = "live@example.com"
    make_verified(email)
    with pytest.raises(ValidationFailed):
        account_services.register_user(email=email, password=STRONG_PASSWORD, name="Other")


@pytest.mark.django_db
def test_reregister_case_insensitive():
    email = "CaseMix@Example.com"
    user = make_verified(email)
    old_pk = user.pk
    account_services.close_account(user, password=STRONG_PASSWORD)
    new_user = account_services.register_user(
        email="casemix@example.com", password=STRONG_PASSWORD, name="Again"
    )
    assert new_user.pk != old_pk
    assert new_user.email == "casemix@example.com"


@pytest.mark.django_db
def test_financial_records_preserved_after_owner_close(world):
    owner = make_closable_owner(world)
    original_pk = owner.pk
    payment_ids = list(Payment.objects.filter(recorded_by=owner).values_list("pk", flat=True))
    due_ids = list(Due.objects.filter(member__user=owner).values_list("pk", flat=True))
    sub_id = world["plan_x"].pk
    assert Subscription.all_with_archived.filter(pk=sub_id, owner_id=original_pk).exists()

    account_services.close_account(owner, password=STRONG_PASSWORD)

    assert User.objects.get(pk=original_pk).is_active is False
    assert Subscription.all_with_archived.filter(pk=sub_id, owner_id=original_pk).exists()
    assert Payment.objects.filter(pk__in=payment_ids, recorded_by_id=original_pk).count() == len(payment_ids)
    assert Due.objects.filter(pk__in=due_ids).count() == len(due_ids)
    assert AuditLog.objects.filter(user_id=original_pk).exists()
    if Statement.objects.filter(user_id=original_pk).exists():
        assert Statement.objects.filter(user_id=original_pk).count() > 0

    fresh = make_verified("new-owner@example.com")
    assert not Subscription.objects.filter(owner=fresh, pk=sub_id).exists()
    assert not Payment.objects.filter(recorded_by=fresh, pk__in=payment_ids).exists()


@pytest.mark.django_db
def test_closure_failed_leaves_account_unchanged(world):
    user = world["member"]
    before_email = user.email
    with pytest.raises(ConflictError):
        account_services.close_account(user, password=STRONG_PASSWORD)
    user.refresh_from_db()
    assert user.email == before_email
    assert user.is_active is True


@pytest.mark.django_db(transaction=True)
def test_concurrent_register_same_email_after_closure():
    email = "race-reg@example.com"
    user = make_verified(email)
    account_services.close_account(user, password=STRONG_PASSWORD)
    cache.clear()
    clear_password_confirm_success(user.pk)

    def try_register():
        return account_services.register_user(email=email, password=STRONG_PASSWORD, name="Race")

    results, errors = run_concurrently([try_register] * 4, transaction=True)
    assert sum(1 for r in results if r is not None) == 1
    assert all(isinstance(e, ValidationFailed) and e.code == "validation_failed" for e in errors if e is not None)
    assert User.objects.filter(email__iexact=email, is_active=True).count() == 1


@pytest.mark.django_db
def test_close_cancels_pending_email_change_only_for_user(world):
    user = world["outsider"]
    other = make_verified("other-email-change@example.com")
    user.pending_email = "new-outsider@example.com"
    user.save(update_fields=["pending_email"])
    other.pending_email = "other-pending@example.com"
    other.save(update_fields=["pending_email"])
    with transaction.atomic():
        pending_row = enqueue_outbound_email(
            email_type=OutboundEmailType.EMAIL_CHANGE,
            business_event_id=f"email_change:closure:{user.pk}",
            to_email=user.pending_email,
            user=user,
        )
        other_row = enqueue_outbound_email(
            email_type=OutboundEmailType.EMAIL_CHANGE,
            business_event_id=f"email_change:closure:{other.pk}",
            to_email=other.pending_email,
            user=other,
        )
        sent_row = enqueue_outbound_email(
            email_type=OutboundEmailType.EMAIL_CHANGE,
            business_event_id=f"email_change:sent:{user.pk}",
            to_email="was-pending@example.com",
            user=user,
        )
        sent_row.status = OutboundEmailStatus.SENT
        sent_row.save(update_fields=["status"])
        verify_row = enqueue_outbound_email(
            email_type=OutboundEmailType.ACCOUNT_VERIFY,
            business_event_id=f"verify:{user.pk}",
            to_email=user.email,
            user=user,
        )

    account_services.close_account(user, password=STRONG_PASSWORD)

    pending_row.refresh_from_db()
    other_row.refresh_from_db()
    sent_row.refresh_from_db()
    verify_row.refresh_from_db()
    assert pending_row.status == OutboundEmailStatus.CANCELLED
    assert other_row.status == OutboundEmailStatus.PENDING
    assert sent_row.status == OutboundEmailStatus.SENT
    assert verify_row.status == OutboundEmailStatus.CANCELLED


@pytest.mark.django_db(transaction=True)
def test_concurrent_close_one_consistent_state():
    user = make_verified("concurrent-close@example.com")
    original_email = user.email
    pk = user.pk

    def close_once():
        account_services.close_account(User.objects.get(pk=pk), password=STRONG_PASSWORD)

    results, errors = run_concurrently([close_once, close_once], transaction=True)
    assert sum(1 for e in errors if e is None) == 1
    closed = [e for e in errors if isinstance(e, ConflictError) and e.code == "account_already_closed"]
    assert len(closed) == 1
    closed_user = User.objects.get(pk=pk)
    assert closed_user.is_active is False
    assert closed_user.email.endswith(f"@{account_services.ACCOUNT_TOMBSTONE_DOMAIN}")
    assert not User.objects.filter(email__iexact=original_email).exists()
    assert User.objects.filter(pk=pk).count() == 1