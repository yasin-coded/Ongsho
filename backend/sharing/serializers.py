from django.utils import timezone

from core.money import format_bdt
from sharing import selectors
from sharing.models import Invite, Member
from sharing.services import _invite_share_message, _per_seat_bdt


def _user_public(user) -> dict:
    return {"id": user.pk, "name": user.name}


def invite_row(invite: Invite) -> dict:
    return {
        "id": invite.pk,
        "email": invite.email,
        "status": selectors.invite_display_status(invite),
        "created_at": invite.created_at,
        "expires_on": invite.expires_on,
        "invited_by": _user_public(invite.invited_by),
        "accepted_by": _user_public(invite.accepted_by) if invite.accepted_by_id else None,
        "replaces_member": invite.replaces_member_id,
    }


def member_row(member: Member, *, due_ctx: dict | None = None) -> dict:
    row = {
        "id": member.pk,
        "user_id": member.user_id,
        "name": member.user.name,
        "first_name": (member.user.name or "").split(" ")[0],
        "email": member.user.email,
        "avatar_id": member.user.avatar_id,
        "is_owner_seat": selectors.is_owner_seat(member),
        "status": member.status,
        "joined_on": member.joined_on,
        "left_on": member.left_on,
        "share_type": member.share_type,
        "share_value": str(member.share_value) if member.share_value is not None else None,
        "leave_requested_at": member.leave_requested_at,
        "due_id": None,
        "due_status": None,
        "due_amount": None,
        "last_payment": None,
        "pending_payment_id": None,
    }
    if due_ctx:
        row.update(due_ctx)
    return row


def member_detail_row(member: Member, *, due_ctx: dict | None = None, rows: list | None = None) -> dict:
    data = member_row(member, due_ctx=due_ctx)
    sub = member.shared_plan.subscription
    data["plan_id"] = sub.pk
    data["plan_name"] = sub.plan_name
    data["rows"] = rows if rows is not None else []
    return data


def me_invite_row(invite: Invite) -> dict:
    shared = invite.shared_plan
    sub = shared.subscription
    per = _per_seat_bdt(shared)
    share = str(per) if per is not None else None
    return {
        "id": invite.pk,
        "plan_name": sub.plan_name,
        "from": _first_name(invite.invited_by),
        "seats": shared.seats,
        "share": share if share else _invite_share_message(shared),
        "expires_on": invite.expires_on,
    }


def _first_name(user) -> str:
    return ((user.name or "").strip().split(" ") or [""])[0] or (user.name or "")
