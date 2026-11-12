from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone

from core.exceptions import NotFound
from plans.models import PlanMode
from plans.selectors import owned_subscription
from sharing.models import Invite, InviteStatus, Member, MemberStatus, SharedPlan, SplitType

User = get_user_model()


def shared_plan_for_owner(user, plan_id: int) -> SharedPlan:
    sub = owned_subscription(user, plan_id)
    try:
        return SharedPlan.objects.select_related("subscription").get(subscription=sub)
    except SharedPlan.DoesNotExist:
        raise NotFound("Plan not found.") from None


def invite_for_owner(user, invite_id: int) -> Invite:
    invite = (
        Invite.objects.select_related("shared_plan__subscription", "invited_by", "accepted_by", "replaces_member")
        .filter(pk=invite_id, shared_plan__subscription__owner=user)
        .first()
    )
    if invite is None:
        raise NotFound("Not found.")
    return invite


def invite_by_token(raw_token: str) -> Invite:
    from sharing.tokens import hash_invite_token

    token_hash = hash_invite_token(raw_token)
    invite = (
        Invite.objects.select_related(
            "shared_plan__subscription",
            "shared_plan__subscription__owner",
            "invited_by",
        )
        .filter(token_hash=token_hash)
        .first()
    )
    if invite is None:
        raise NotFound("Not found.")
    return invite


def invite_for_recipient(user, invite_id: int) -> Invite | None:
    return Invite.objects.filter(pk=invite_id, email=user.email.lower()).first()


def invite_for_user_pending(user) -> list[Invite]:
    if not user.email_verified:
        return []
    email = user.email.lower()
    return list(
        Invite.objects.select_related("shared_plan__subscription", "invited_by")
        .filter(email=email, status=InviteStatus.PENDING, expires_on__gt=timezone.now())
        .order_by("-created_at", "-id")
    )


def member_for_owner(user, member_id: int) -> Member:
    member = (
        Member.objects.select_related("user", "shared_plan__subscription")
        .filter(pk=member_id, shared_plan__subscription__owner=user)
        .first()
    )
    if member is None:
        raise NotFound("Not found.")
    return member


def active_member_for_user(user, plan_id: int) -> Member:
    member = (
        Member.objects.select_related("shared_plan__subscription")
        .filter(
            user=user,
            shared_plan__subscription_id=plan_id,
            status__in=(MemberStatus.ACTIVE, MemberStatus.LEAVE_REQUESTED),
        )
        .first()
    )
    if member is None:
        raise NotFound("Not found.")
    return member


def members_queryset(shared: SharedPlan, *, include_left: bool = False):
    qs = Member.objects.filter(shared_plan=shared).select_related("user")
    if not include_left:
        qs = qs.exclude(status=MemberStatus.LEFT)
    sub = shared.subscription
    if sub.plan_mode == PlanMode.OWNER:
        qs = qs.annotate(
            sort_owner=Case(
                When(user_id=sub.owner_id, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by("sort_owner", "joined_on", "id")
    else:
        qs = qs.order_by("joined_on", "id")
    return qs


def invite_display_status(invite: Invite) -> str:
    if invite.status == InviteStatus.PENDING and invite.expires_on <= timezone.now():
        return "expired"
    return invite.status


def pending_invite_count(shared: SharedPlan) -> int:
    return Invite.objects.filter(shared_plan=shared, status=InviteStatus.PENDING).count()


def member_count_active(shared: SharedPlan) -> int:
    return Member.objects.filter(shared_plan=shared).exclude(status=MemberStatus.LEFT).count()


def is_owner_seat(member: Member) -> bool:
    return member.user_id == member.shared_plan.subscription.owner_id
