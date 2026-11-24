from django.db.models import Exists, OuterRef, Q

from core.exceptions import ConflictError, Forbidden
from dues.models import Due, DueStatus
from notifications.models import Notification
from payments.models import Payment, ReviewStatus
from plans.models import Subscription
from sharing.models import Member, MemberStatus, OwnershipTransfer, TransferStatus


def assert_account_closure_allowed(user) -> None:
    if user.is_staff or user.is_superuser:
        raise Forbidden(
            "Staff accounts cannot be closed through the app.",
            code="staff_cannot_close",
        )
    if OwnershipTransfer.objects.filter(
        status=TransferStatus.PENDING,
    ).filter(Q(from_user=user) | Q(to_user=user)).exists():
        raise ConflictError(
            "Finish or cancel your pending ownership transfer before closing your account.",
            code="pending_ownership_transfer",
        )
    if Subscription.objects.filter(owner=user, archived_on__isnull=True).exists():
        raise ConflictError(
            "You still have active plans. Archive or delete them before closing your account.",
            code="owned_plans_remain",
        )
    if Member.objects.filter(
        user=user,
        status__in=(MemberStatus.ACTIVE, MemberStatus.LEAVE_REQUESTED),
        shared_plan__subscription__archived_on__isnull=True,
    ).exists():
        raise ConflictError(
            "Leave or resolve your shared-plan memberships before closing your account.",
            code="active_membership",
        )


def plans_owned_count(user) -> int:
    return Subscription.objects.filter(owner=user).count()


def plans_joined_count(user) -> int:
    return (
        Subscription.objects.filter(
            archived_on__isnull=True,
            shared_plan__members__user=user,
            shared_plan__members__status__in=(
                MemberStatus.ACTIVE,
                MemberStatus.LEAVE_REQUESTED,
            ),
        )
        .exclude(owner=user)
        .distinct()
        .count()
    )


def nav_counts(user) -> dict[str, int]:
    pending_payments = Payment.objects.filter(
        shared_plan__subscription__owner=user,
        review_status=ReviewStatus.PENDING,
    )
    reviews = pending_payments.count()

    member_with_due = Member.objects.filter(
        user=user,
        shared_plan__subscription_id=OuterRef("pk"),
        status__in=(
            MemberStatus.ACTIVE,
            MemberStatus.LEAVE_REQUESTED,
        ),
        dues__status=DueStatus.DUE,
    )
    due_plans = (
        Subscription.objects.filter(archived_on__isnull=True)
        .annotate(_member_due=Exists(member_with_due))
        .filter(_member_due=True)
        .exclude(owner=user)
    )
    dues = due_plans.count()

    from notifications.selectors import visible_notifications_qs

    unread = visible_notifications_qs(user).filter(read_at__isnull=True).count()
    return {"reviews": reviews, "dues": dues, "unread": unread}
