from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone

from audit import services as audit_services
from accounts.constants import DEFAULT_AVATAR_ID
from core.exceptions import ConflictError, Forbidden, NotFound, ValidationFailed
from core.money import format_bdt, quantize_money
from plans.models import PlanMode, PriceChange, Subscription
from plans.selectors import owned_subscription, price_now_dict
from sharing.emails import send_invite_email
from sharing.models import Invite, InviteStatus, Member, MemberStatus, SharedPlan, SplitType
from sharing.tokens import hash_invite_token, new_invite_token

User = get_user_model()
EMAIL_RE = re.compile(r"^[^@]+@[^@]+\.[^@]+$")


def _first_name(user) -> str:
    return ((user.name or "").strip().split(" ") or [""])[0] or (user.name or "")


def _audit(user, action: str, entity_type: str, entity_id: int, summary: str, *, plan_id: int) -> None:
    audit_services.log(user, action, entity_type, entity_id, None, None, plan_id=plan_id, summary=summary)


def _per_seat_bdt(shared: SharedPlan) -> Decimal | None:
    data = price_now_dict(shared.subscription)
    if not data:
        return None
    amount_bdt = Decimal(str(data["amount_bdt"]))
    if shared.split_type != SplitType.EQUAL:
        return None
    return quantize_money(amount_bdt / Decimal(shared.seats))


def _invite_share_message(shared: SharedPlan) -> str:
    per = _per_seat_bdt(shared)
    if per is not None:
        return f"{format_bdt(per)} share a month"
    return "the owner will set your amount"


def _not_left_members(shared: SharedPlan):
    return Member.objects.filter(shared_plan=shared).exclude(status=MemberStatus.LEFT)


def _pending_non_replacement_invites(shared: SharedPlan):
    return Invite.objects.filter(
        shared_plan=shared,
        status=InviteStatus.PENDING,
        replaces_member__isnull=True,
    )


def _seat_usage(shared: SharedPlan) -> int:
    return _not_left_members(shared).count() + _pending_non_replacement_invites(shared).count()


def _validate_email_address(email: str) -> str:
    email = (email or "").strip().lower()
    if not email or not EMAIL_RE.match(email):
        raise ValidationFailed("Enter a valid email.", fields={"email": ["Enter a valid email."]})
    return email


def validate_invite_emails_for_new_plan(
    *,
    owner,
    plan_mode: str,
    seats: int,
    invite_emails: list[str],
) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in invite_emails or []:
        email = _validate_email_address(raw)
        if email in seen:
            raise ValidationFailed(
                "Duplicate email in the list.",
                fields={"invite_emails": ["Duplicate email in the list."]},
            )
        seen.add(email)
        normalized.append(email)
        if email == owner.email.lower():
            raise ValidationFailed(
                "You cannot invite your own email.",
                fields={"invite_emails": ["You cannot invite your own email."]},
            )
    min_seats = 2 if plan_mode == PlanMode.OWNER else 1
    if seats < min_seats:
        raise ValidationFailed(
            "Invalid seats for this plan mode.",
            fields={"seats": [f"Seats must be at least {min_seats}."]},
        )
    owner_seat = 1 if plan_mode == PlanMode.OWNER else 0
    if owner_seat + len(normalized) > seats:
        raise ValidationFailed(
            "All seats are taken or already invited.",
            fields={"invite_emails": ["All seats are taken or already invited."]},
        )
    return normalized


def _ensure_not_shared(sub: Subscription) -> None:
    if SharedPlan.objects.filter(subscription=sub).exists():
        raise ConflictError("This plan is already shared.", code="already_shared")


def _owner_joined_on(sub: Subscription, today: date) -> date:
    start = sub.start_date
    return start if start < today else today


def _create_owner_seat(shared: SharedPlan, *, today: date) -> Member:
    sub = shared.subscription
    return Member.objects.create(
        shared_plan=shared,
        user=sub.owner,
        share_type=shared.split_type,
        share_value=None if shared.split_type == SplitType.EQUAL else None,
        status=MemberStatus.ACTIVE,
        joined_on=_owner_joined_on(sub, today),
    )


@transaction.atomic
def share_plan(user, plan_id: int, *, split_type: str, seats: int, today: date) -> SharedPlan:
    sub = (
        Subscription.objects.select_for_update()
        .filter(owner=user, pk=plan_id, archived_on__isnull=True)
        .first()
    )
    if sub is None:
        raise NotFound("Plan not found.")
    _ensure_not_shared(sub)
    if split_type not in {SplitType.EQUAL, SplitType.CUSTOM}:
        raise ValidationFailed("Invalid split type.", fields={"split_type": ["Invalid split type."]})
    if not (1 <= seats <= 20):
        raise ValidationFailed("Seats must be between 1 and 20.", fields={"seats": ["Seats must be between 1 and 20."]})
    if sub.plan_mode == PlanMode.OWNER and seats < 2:
        raise ValidationFailed(
            "Owner plans need at least 2 seats.",
            fields={"seats": ["Owner plans need at least 2 seats."]},
        )
    shared = SharedPlan.objects.create(subscription=sub, split_type=split_type, seats=seats)
    if sub.plan_mode == PlanMode.OWNER:
        _create_owner_seat(shared, today=today)
    _audit(
        user,
        "shared_plan.created",
        "SharedPlan",
        shared.pk,
        f"You made {sub.plan_name} a shared plan with {seats} seats",
        plan_id=sub.pk,
    )
    return shared


@transaction.atomic
def bootstrap_shared_plan(
    user,
    sub: Subscription,
    *,
    split_type: str | None,
    seats: int | None,
    invite_emails: list[str] | None,
    today: date,
) -> SharedPlan:
    split = split_type or SplitType.EQUAL
    seat_count = seats if seats is not None else 2
    emails = invite_emails or []
    if sub.plan_mode == PlanMode.RESELLER:
        seat_count = seats if seats is not None else 2
    validate_invite_emails_for_new_plan(
        owner=user,
        plan_mode=sub.plan_mode,
        seats=seat_count,
        invite_emails=emails,
    )
    shared = SharedPlan.objects.create(subscription=sub, split_type=split, seats=seat_count)
    if sub.plan_mode == PlanMode.OWNER:
        _create_owner_seat(shared, today=today)
    _audit(
        user,
        "shared_plan.created",
        "SharedPlan",
        shared.pk,
        f"You made {sub.plan_name} a shared plan with {seat_count} seats",
        plan_id=sub.pk,
    )
    for email in emails:
        _create_invite_locked(user, shared, email, today, replaces_member=None)
    return shared


@transaction.atomic
def update_seats(user, plan_id: int, *, seats: int) -> SharedPlan:
    shared = (
        SharedPlan.objects.select_for_update()
        .select_related("subscription")
        .filter(subscription__owner=user, subscription_id=plan_id, subscription__archived_on__isnull=True)
        .first()
    )
    if shared is None:
        raise NotFound("Plan not found.")
    if not (1 <= seats <= 20):
        raise ValidationFailed("Seats must be between 1 and 20.", fields={"seats": ["Seats must be between 1 and 20."]})
    members = _not_left_members(shared).count()
    if seats < members:
        raise ValidationFailed(
            "Seats cannot be below the current member count.",
            fields={"seats": ["Seats cannot be below the current member count."]},
        )
    old = shared.seats
    shared.seats = seats
    shared.save(update_fields=["seats"])
    _audit(
        user,
        "shared_plan.seats",
        "SharedPlan",
        shared.pk,
        f"You changed seats from {old} to {seats} on {shared.subscription.plan_name}",
        plan_id=shared.subscription_id,
    )
    return shared


def _expires_end_of_day(today: date) -> datetime:
    naive_end = datetime.combine(today + timedelta(days=settings.INVITE_DAYS), datetime.max.time()).replace(
        microsecond=0
    )
    if timezone.is_naive(naive_end):
        return timezone.make_aware(naive_end, timezone.get_current_timezone())
    return naive_end


def _invite_link(raw_token: str) -> str:
    return f"{settings.FRONTEND_BASE_URL}/invite/{raw_token}"


def _notify_invite(user, invite: Invite, shared: SharedPlan) -> None:
    from core.notify import notify

    sub = shared.subscription
    inviter = invite.invited_by
    message = (
        f"{sub.plan_name} · shared plan · {shared.seats} seats · {_invite_share_message(shared)}"
    )
    notify(
        user,
        "invite",
        f"Invite from {_first_name(inviter)}",
        message,
        link=f"/app/invites/{invite.pk}",
        payload={
            "action": {"type": "invite", "invite_id": invite.pk, "plan_id": sub.pk},
            "plan_id": sub.pk,
        },
    )


def _create_invite_locked(
    owner,
    shared: SharedPlan,
    email: str,
    today: date,
    *,
    replaces_member: Member | None,
    skip_capacity: bool = False,
) -> tuple[Invite, str]:
    email = _validate_email_address(email)
    sub = shared.subscription
    if email == sub.owner.email.lower():
        raise ValidationFailed("You cannot invite your own email.", fields={"email": ["You cannot invite your own email."]})
    if _not_left_members(shared).filter(user__email__iexact=email).exists():
        raise ValidationFailed(
            "That person is already a member.",
            fields={"email": ["That person is already a member."]},
        )
    if Invite.objects.filter(shared_plan=shared, email=email, status=InviteStatus.PENDING).exists():
        raise ConflictError("An invite for this email is already pending.", code="invite_exists")
    if not skip_capacity and replaces_member is None and _seat_usage(shared) >= shared.seats:
        raise ValidationFailed(
            "All seats are taken or already invited.",
            code="plan_full",
            fields={"email": ["All seats are taken or already invited."]},
        )
    raw, token_hash = new_invite_token()
    invite = Invite.objects.create(
        shared_plan=shared,
        invited_by=owner,
        email=email,
        token_hash=token_hash,
        expires_on=_expires_end_of_day(today),
        status=InviteStatus.PENDING,
        replaces_member=replaces_member,
    )
    send_invite_email(
        to_email=email,
        plan_name=sub.plan_name,
        inviter_name=owner.name,
        invite_link=_invite_link(raw),
    )
    if User.objects.filter(email__iexact=email, email_verified=True).exists():
        existing = User.objects.get(email__iexact=email)
        _notify_invite(existing, invite, shared)
    _audit(
        owner,
        "invite.created",
        "Invite",
        invite.pk,
        f"You invited {email} to {sub.plan_name}",
        plan_id=sub.pk,
    )
    return invite, raw


@transaction.atomic
def create_invite(user, plan_id: int, *, email: str, today: date) -> tuple[Invite, str]:
    shared = (
        SharedPlan.objects.select_for_update()
        .select_related("subscription")
        .filter(subscription__owner=user, subscription_id=plan_id)
        .first()
    )
    if shared is None:
        raise NotFound("Plan not found.")
    return _create_invite_locked(user, shared, email, today, replaces_member=None)


@transaction.atomic
def cancel_invite(user, invite_id: int) -> Invite:
    invite = (
        Invite.objects.select_for_update()
        .select_related("shared_plan__subscription")
        .filter(pk=invite_id, shared_plan__subscription__owner=user)
        .first()
    )
    if invite is None:
        raise NotFound("Not found.")
    if invite.status != InviteStatus.PENDING:
        raise ConflictError("Only pending invites can be cancelled.", code="invite_used")
    invite.status = InviteStatus.CANCELLED
    invite.save(update_fields=["status"])
    from core.notify import resolve_notifications

    resolve_notifications("invite", invite_id=invite.pk)
    _audit(
        user,
        "invite.cancelled",
        "Invite",
        invite.pk,
        f"You cancelled the invite to {invite.email}",
        plan_id=invite.shared_plan.subscription_id,
    )
    return invite


@transaction.atomic
def new_invite_link(user, invite_id: int, *, today: date) -> tuple[Invite, str]:
    invite = (
        Invite.objects.select_for_update()
        .select_related("shared_plan__subscription", "invited_by")
        .filter(pk=invite_id, shared_plan__subscription__owner=user)
        .first()
    )
    if invite is None:
        raise NotFound("Not found.")
    if invite.status != InviteStatus.PENDING:
        raise ConflictError("Only pending invites can get a new link.", code="invite_used")
    raw, token_hash = new_invite_token()
    invite.token_hash = token_hash
    invite.expires_on = _expires_end_of_day(today)
    invite.save(update_fields=["token_hash", "expires_on"])
    sub = invite.shared_plan.subscription
    send_invite_email(
        to_email=invite.email,
        plan_name=sub.plan_name,
        inviter_name=invite.invited_by.name,
        invite_link=_invite_link(raw),
    )
    _audit(
        user,
        "invite.new_link",
        "Invite",
        invite.pk,
        f"You sent a new invite link to {invite.email}",
        plan_id=sub.pk,
    )
    return invite, raw


def _lock_invite(*, invite_id: int | None, token: str | None) -> Invite:
    qs = Invite.objects.select_for_update(of=("self",))
    if token:
        invite = qs.filter(token_hash=hash_invite_token(token)).first()
    elif invite_id is not None:
        invite = qs.filter(pk=invite_id).first()
    else:
        raise NotFound("Not found.")
    if invite is None:
        raise NotFound("Not found.")
    return Invite.objects.select_related(
        "shared_plan__subscription", "invited_by", "replaces_member"
    ).get(pk=invite.pk)


@transaction.atomic
def accept_invite(user, *, today: date, invite_id: int | None = None, token: str | None = None) -> dict:
    invite = _lock_invite(invite_id=invite_id, token=token)
    if invite.status != InviteStatus.PENDING:
        raise ConflictError("This invite is no longer available.", code="invite_used")
    if invite.expires_on <= timezone.now():
        raise ConflictError("This invite has expired.", code="invite_expired", status_code=410)
    if user.email.lower() != invite.email:
        raise Forbidden("This invite was sent to a different email address.", code="wrong_email")
    shared = invite.shared_plan
    sub = shared.subscription
    replacing = invite.replaces_member
    if replacing is None and _not_left_members(shared).count() >= shared.seats:
        raise ConflictError("This plan is full.", code="plan_full")
    if replacing is not None:
        replacing = Member.objects.select_for_update().get(pk=replacing.pk)
    member = Member.objects.create(
        shared_plan=shared,
        user=user,
        share_type=replacing.share_type if replacing else shared.split_type,
        share_value=replacing.share_value if replacing else None,
        status=MemberStatus.ACTIVE,
        joined_on=today,
    )
    invite.status = InviteStatus.ACCEPTED
    invite.accepted_by = user
    invite.save(update_fields=["status", "accepted_by"])
    if replacing is not None:
        replacing.status = MemberStatus.LEFT
        replacing.left_on = today
        replacing.save(update_fields=["status", "left_on"])
    from core.notify import notify, resolve_notifications
    from core.signals import member_joined

    resolve_notifications("invite", invite_id=invite.pk)
    taken = _not_left_members(shared).count()
    notify(
        sub.owner,
        "invite_accepted",
        f"{_first_name(user)} joined {sub.plan_name}",
        f"{sub.plan_name} · {taken} of {shared.seats} seats taken",
        link=f"/app/plans/{sub.pk}",
        payload={"plan_id": sub.pk},
    )
    member_joined.send(sender=type(member), member=member, today=today)
    _audit(
        user,
        "invite.accepted",
        "Invite",
        invite.pk,
        f"{user.name} joined the plan",
        plan_id=sub.pk,
    )
    return {"plan_id": sub.pk, "message": f"You joined {sub.plan_name}."}


@transaction.atomic
def decline_invite(user, *, invite_id: int | None = None, token: str | None = None) -> dict:
    invite = _lock_invite(invite_id=invite_id, token=token)
    if invite.status != InviteStatus.PENDING:
        raise ConflictError("This invite is no longer available.", code="invite_used")
    if user.email.lower() != invite.email:
        raise Forbidden("This invite was sent to a different email address.", code="wrong_email")
    invite.status = InviteStatus.DECLINED
    invite.save(update_fields=["status"])
    sub = invite.shared_plan.subscription
    from core.notify import notify, resolve_notifications

    resolve_notifications("invite", invite_id=invite.pk)
    notify(
        sub.owner,
        "invite_declined",
        f"{_first_name(user)} declined your invite",
        sub.plan_name,
        link=f"/app/plans/{sub.pk}",
        payload={"plan_id": sub.pk},
    )
    _audit(
        user,
        "invite.declined",
        "Invite",
        invite.pk,
        f"{user.name} declined the invite",
        plan_id=sub.pk,
    )
    return {"plan_id": sub.pk, "message": "Invite declined."}


@transaction.atomic
def signup_via_invite(*, token: str, name: str, password: str, today: date):
    invite = _lock_invite(invite_id=None, token=token)
    if invite.status != InviteStatus.PENDING:
        raise ConflictError("This invite is no longer available.", code="invite_used")
    if invite.expires_on <= timezone.now():
        raise ConflictError("This invite has expired.", code="invite_expired", status_code=410)
    if User.objects.filter(email__iexact=invite.email).exists():
        raise ConflictError("An account already exists for this email.", code="account_exists")
    name = (name or "").strip()
    if not name:
        raise ValidationFailed("Enter your name.", fields={"name": ["Enter your name."]})
    try:
        validate_password(password)
    except DjangoValidationError as exc:
        raise ValidationFailed("Invalid password.", fields={"password": list(exc.messages)}) from exc
    user = User.objects.create_user(
        email=invite.email,
        password=password,
        name=name,
        email_verified=True,
        avatar_id=DEFAULT_AVATAR_ID,
    )
    result = accept_invite(user, today=today, token=token)
    from accounts import services as account_services

    access, refresh, user = account_services.login_user(email=user.email, password=password)
    return access, refresh, user, result["plan_id"]


@transaction.atomic
def request_leave(user, plan_id: int, *, today: date) -> Member:
    member = (
        Member.objects.select_for_update()
        .select_related("shared_plan__subscription", "user")
        .filter(
            user=user,
            shared_plan__subscription_id=plan_id,
            status=MemberStatus.ACTIVE,
        )
        .first()
    )
    if member is None:
        raise NotFound("Not found.")
    if member.user_id == member.shared_plan.subscription.owner_id:
        raise ConflictError("The plan owner cannot request to leave.", code="owner_cannot_leave")
    member.status = MemberStatus.LEAVE_REQUESTED
    member.leave_requested_at = timezone.now()
    member.save(update_fields=["status", "leave_requested_at"])
    sub = member.shared_plan.subscription
    from core.notify import notify

    notify(
        sub.owner,
        "leave_request",
        f"{_first_name(user)} wants to leave",
        f"{sub.plan_name} · needs your OK before the next renewal",
        link=f"/app/plans/{sub.pk}?leave={member.pk}",
        payload={
            "action": {"type": "leave", "member_id": member.pk, "plan_id": sub.pk},
            "plan_id": sub.pk,
        },
    )
    _audit(
        user,
        "member.leave_requested",
        "Member",
        member.pk,
        f"{user.name} requested to leave {sub.plan_name}",
        plan_id=sub.pk,
    )
    return member


@transaction.atomic
def cancel_leave_request(user, plan_id: int) -> Member:
    member = (
        Member.objects.select_for_update()
        .select_related("shared_plan__subscription")
        .filter(user=user, shared_plan__subscription_id=plan_id, status=MemberStatus.LEAVE_REQUESTED)
        .first()
    )
    if member is None:
        raise ConflictError("There is no leave request to cancel.", code="no_request")
    member.status = MemberStatus.ACTIVE
    member.leave_requested_at = None
    member.save(update_fields=["status", "leave_requested_at"])
    from core.notify import resolve_notifications

    resolve_notifications("leave", member_id=member.pk)
    sub = member.shared_plan.subscription
    _audit(
        user,
        "member.leave_cancelled",
        "Member",
        member.pk,
        f"{user.name} cancelled their leave request",
        plan_id=sub.pk,
    )
    return member


@transaction.atomic
def owner_leave_decision(
    owner,
    member_id: int,
    *,
    today: date,
    approve: bool,
    leave_date: date | None = None,
    unpaid: str | None = None,
) -> Member:
    member = (
        Member.objects.select_for_update()
        .select_related("shared_plan__subscription", "user")
        .filter(pk=member_id, shared_plan__subscription__owner=owner)
        .first()
    )
    if member is None:
        raise NotFound("Not found.")
    if member.user_id == member.shared_plan.subscription.owner_id:
        raise ConflictError("The owner seat cannot leave.", code="owner_cannot_leave")
    sub = member.shared_plan.subscription
    from core.notify import notify, resolve_notifications

    if approve:
        if member.status not in (MemberStatus.ACTIVE, MemberStatus.LEAVE_REQUESTED):
            raise ConflictError("This member cannot leave.", code="invalid_member_status")
        if leave_date is None or unpaid not in {"keep", "waive"}:
            raise ValidationFailed(
                "Leave date and unpaid choice are required.",
                fields={
                    **({"leave_date": ["This field is required."]} if leave_date is None else {}),
                    **({"unpaid": ["Must be keep or waive."]} if unpaid not in {"keep", "waive"} else {}),
                },
            )
        if leave_date < today or leave_date > today + timedelta(days=90):
            raise ValidationFailed(
                "Leave date must be between today and 90 days ahead.",
                fields={"leave_date": ["Leave date must be between today and 90 days ahead."]},
            )
        was_requested = member.status == MemberStatus.LEAVE_REQUESTED
        member.left_on = leave_date
        update_fields = ["left_on"]
        if leave_date == today:
            member.status = MemberStatus.LEFT
            member.leave_requested_at = None
            update_fields.extend(["status", "leave_requested_at"])
        member.save(update_fields=update_fields)
        from core.signals import member_leaving

        member_leaving.send(sender=type(member), member=member, leave_date=leave_date, unpaid=unpaid, today=today)
        resolve_notifications("leave", member_id=member.pk)
        notify(
            member.user,
            "leave_result",
            f"You are leaving {sub.plan_name}",
            f"Your last cycle is the one that starts before {leave_date}.",
            link=f"/app/shared-plans/{sub.pk}",
            payload={"plan_id": sub.pk},
        )
        summary = (
            f"You approved {_first_name(member.user)}'s request to leave from {leave_date}"
            if was_requested
            else f"You removed {_first_name(member.user)} from {leave_date}"
        )
        _audit(owner, "member.leave_approved", "Member", member.pk, summary, plan_id=sub.pk)
        return member

    if member.status != MemberStatus.LEAVE_REQUESTED:
        raise ConflictError("Only a pending leave request can be declined.", code="no_request")
    member.status = MemberStatus.ACTIVE
    member.leave_requested_at = None
    member.save(update_fields=["status", "leave_requested_at"])
    resolve_notifications("leave", member_id=member.pk)
    notify(
        member.user,
        "leave_result",
        f"{_first_name(sub.owner)} asked you to stay",
        f"{sub.plan_name} · your leave request was declined",
        link=f"/app/shared-plans/{sub.pk}",
        payload={"plan_id": sub.pk},
    )
    _audit(
        owner,
        "member.leave_declined",
        "Member",
        member.pk,
        f"You declined {_first_name(member.user)}'s leave request",
        plan_id=sub.pk,
    )
    return member


@transaction.atomic
def replace_member(user, member_id: int, *, email: str, today: date) -> tuple[Invite, str]:
    member = (
        Member.objects.select_for_update()
        .select_related("shared_plan__subscription")
        .filter(pk=member_id, shared_plan__subscription__owner=user)
        .first()
    )
    if member is None:
        raise NotFound("Not found.")
    if member.user_id == member.shared_plan.subscription.owner_id:
        raise ConflictError("The owner seat cannot be replaced.", code="owner_cannot_leave")
    if member.status not in (MemberStatus.ACTIVE, MemberStatus.LEAVE_REQUESTED):
        raise ConflictError("This member cannot be replaced.", code="invalid_member_status")
    if Invite.objects.filter(
        shared_plan=member.shared_plan,
        status=InviteStatus.PENDING,
        replaces_member=member,
    ).exists():
        raise ConflictError("A replacement invite is already pending.", code="replacement_pending")
    shared = SharedPlan.objects.select_for_update().get(pk=member.shared_plan_id)
    return _create_invite_locked(
        user, shared, email, today, replaces_member=member, skip_capacity=True
    )


@transaction.atomic
def update_split(user, plan_id: int, *, split_type: str, shares: dict | None, today: date) -> SharedPlan:
    shared = (
        SharedPlan.objects.select_for_update()
        .select_related("subscription")
        .filter(subscription__owner=user, subscription_id=plan_id)
        .first()
    )
    if shared is None:
        raise NotFound("Plan not found.")
    if split_type not in {SplitType.EQUAL, SplitType.CUSTOM}:
        raise ValidationFailed("Invalid split type.", fields={"split_type": ["Invalid split type."]})
    members = list(_not_left_members(shared).select_for_update())
    sub = shared.subscription
    if split_type == SplitType.CUSTOM:
        if not shares:
            raise ValidationFailed("Shares are required.", fields={"shares": ["Shares are required."]})
        price = price_now_dict(sub)
        if not price:
            raise ValidationFailed("Plan price is not set.", fields={"shares": ["Plan price is not set."]})
        total = Decimal(str(price["amount_bdt"]))
        member_ids = {m.pk for m in members}
        if set(shares.keys()) != {str(mid) for mid in member_ids}:
            raise ValidationFailed(
                "Shares must list every active member.",
                fields={"shares": ["Shares must list every active member."]},
            )
        running = Decimal("0")
        parsed: dict[int, Decimal] = {}
        for m in members:
            raw = shares.get(str(m.pk)) or shares.get(m.pk)
            try:
                val = quantize_money(Decimal(str(raw)))
            except Exception:
                raise ValidationFailed(
                    "Enter valid share amounts.",
                    fields={"shares": {str(m.pk): ["Enter a valid amount."]}},
                )
            if val <= 0:
                raise ValidationFailed(
                    "Each share must be greater than zero.",
                    fields={"shares": {str(m.pk): ["Each share must be greater than zero."]}},
                )
            parsed[m.pk] = val
            running += val
        if running != total:
            raise ValidationFailed(
                "Shares must sum to the plan price.",
                fields={"shares": ["Shares must sum to the plan price."]},
            )
        for m in members:
            m.share_type = SplitType.CUSTOM
            m.share_value = parsed[m.pk]
            m.save(update_fields=["share_type", "share_value"])
        shared.split_type = SplitType.CUSTOM
    else:
        for m in members:
            m.share_type = SplitType.EQUAL
            m.share_value = None
            m.save(update_fields=["share_type", "share_value"])
        shared.split_type = SplitType.EQUAL
    shared.save(update_fields=["split_type"])
    from core.signals import split_changed

    split_changed.send(sender=type(shared), plan=sub, today=today)
    _audit(
        user,
        "shared_plan.split",
        "SharedPlan",
        shared.pk,
        f"You updated how {sub.plan_name} is split",
        plan_id=sub.pk,
    )
    return shared


def close_departed_members(today: date) -> int:
    qs = Member.objects.filter(left_on__lte=today).exclude(status=MemberStatus.LEFT)
    return qs.update(status=MemberStatus.LEFT)


def gather_plan_delete_context(sub: Subscription) -> tuple[list[int], SharedPlan | None]:
    shared = SharedPlan.objects.filter(subscription=sub).first()
    if shared is None:
        return [], None
    member_user_ids = list(
        Member.objects.filter(shared_plan=shared)
        .exclude(user=sub.owner)
        .values_list("user_id", flat=True)
    )
    return member_user_ids, shared


def cancel_all_pending_invites(shared: SharedPlan) -> int:
    from core.notify import resolve_notifications

    pending = list(Invite.objects.filter(shared_plan=shared, status=InviteStatus.PENDING))
    for invite in pending:
        invite.status = InviteStatus.CANCELLED
        invite.save(update_fields=["status"])
        resolve_notifications("invite", invite_id=invite.pk)
    return len(pending)


from sharing.ownership_transfer import (  # noqa: E402
    accept_ownership_transfer,
    cancel_ownership_transfer,
    cancel_pending_transfers_for_deleted_plan,
    decline_ownership_transfer,
    start_ownership_transfer,
)
