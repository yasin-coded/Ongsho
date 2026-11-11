from django.db.models import Exists, OuterRef

from dues.models import Due, DueStatus
from notifications.models import Notification
from payments.models import Payment, ReviewStatus
from plans.models import Subscription
from sharing.models import Member, MemberStatus


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

    unread = Notification.objects.filter(user=user, read_at__isnull=True).count()
    return {"reviews": reviews, "dues": dues, "unread": unread}
