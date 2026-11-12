from __future__ import annotations

from django.apps import apps
from django.utils import timezone

from notifications.kinds import PAYMENT_KINDS, PLAN_KINDS, REMINDER_KINDS, group_of
from notifications.models import Notification

LIST_FILTERS = frozenset({"all", "action", "payments", "plans", "reminders"})


def _payments_by_id(ids: set[int]) -> dict[int, object]:
    if not ids:
        return {}
    Payment = apps.get_model("payments", "Payment")
    return Payment.objects.in_bulk(ids)


def _invites_by_id(ids: set[int]) -> dict[int, object]:
    if not ids:
        return {}
    Invite = apps.get_model("sharing", "Invite")
    return Invite.objects.in_bulk(ids)


def _members_by_id(ids: set[int]) -> dict[int, object]:
    if not ids:
        return {}
    Member = apps.get_model("sharing", "Member")
    return Member.objects.in_bulk(ids)


def _transfers_by_id(ids: set[int]) -> dict[int, object]:
    if not ids:
        return {}
    OwnershipTransfer = apps.get_model("sharing", "OwnershipTransfer")
    return OwnershipTransfer.objects.in_bulk(ids)


def _payment_resolved(payment) -> str | None:
    from payments.models import ReviewStatus

    status = payment.review_status
    if status == ReviewStatus.PENDING:
        return None
    if status == ReviewStatus.CONFIRMED:
        return "approved"
    if status == ReviewStatus.REJECTED:
        return "rejected"
    if status == ReviewStatus.REVERSED:
        return "reversed"
    return None


def _invite_resolved(invite) -> str | None:
    from sharing.models import InviteStatus

    status = invite.status
    if status == InviteStatus.PENDING:
        if invite.expires_on < timezone.now():
            return "expired"
        return None
    if status == InviteStatus.ACCEPTED:
        return "joined"
    if status == InviteStatus.DECLINED:
        return "declined"
    if status == InviteStatus.CANCELLED:
        return "cancelled"
    return None


def _leave_resolved(member) -> str | None:
    from sharing.models import MemberStatus

    status = member.status
    if status == MemberStatus.LEAVE_REQUESTED:
        return None
    if status == MemberStatus.LEFT:
        return "approved"
    if status == MemberStatus.ACTIVE:
        return "declined"
    return None


def _transfer_resolved(transfer) -> str | None:
    from sharing.models import TransferStatus

    status = transfer.status
    if status == TransferStatus.PENDING:
        return None
    if status == TransferStatus.ACCEPTED:
        return "accepted"
    if status == TransferStatus.DECLINED:
        return "declined"
    if status == TransferStatus.CANCELLED:
        return "cancelled"
    return None


def resolve_for_notifications(notifications: list[Notification]) -> dict[int, str | None]:
    """Return notification id -> resolved label (None = still open / not applicable)."""
    payment_ids: set[int] = set()
    invite_ids: set[int] = set()
    member_ids: set[int] = set()
    transfer_ids: set[int] = set()
    with_action: list[tuple[int, dict]] = []

    for note in notifications:
        action = (note.payload or {}).get("action")
        if not isinstance(action, dict) or not action.get("type"):
            continue
        with_action.append((note.pk, action))
        action_type = action["type"]
        if action_type == "payment" and action.get("payment_id") is not None:
            payment_ids.add(int(action["payment_id"]))
        elif action_type == "invite" and action.get("invite_id") is not None:
            invite_ids.add(int(action["invite_id"]))
        elif action_type == "leave" and action.get("member_id") is not None:
            member_ids.add(int(action["member_id"]))
        elif action_type == "transfer" and action.get("transfer_id") is not None:
            transfer_ids.add(int(action["transfer_id"]))

    payments = _payments_by_id(payment_ids)
    invites = _invites_by_id(invite_ids)
    members = _members_by_id(member_ids)
    transfers = _transfers_by_id(transfer_ids)

    resolved: dict[int, str | None] = {note.pk: None for note in notifications}

    for note_id, action in with_action:
        action_type = action.get("type")
        if action_type == "payment":
            pid = action.get("payment_id")
            payment = payments.get(int(pid)) if pid is not None else None
            if payment is None:
                resolved[note_id] = "gone"
            else:
                resolved[note_id] = _payment_resolved(payment)
        elif action_type == "invite":
            iid = action.get("invite_id")
            invite = invites.get(int(iid)) if iid is not None else None
            if invite is None:
                resolved[note_id] = "gone"
            else:
                resolved[note_id] = _invite_resolved(invite)
        elif action_type == "leave":
            mid = action.get("member_id")
            member = members.get(int(mid)) if mid is not None else None
            if member is None:
                resolved[note_id] = "gone"
            else:
                resolved[note_id] = _leave_resolved(member)
        elif action_type == "transfer":
            tid = action.get("transfer_id")
            transfer = transfers.get(int(tid)) if tid is not None else None
            if transfer is None:
                resolved[note_id] = "gone"
            else:
                resolved[note_id] = _transfer_resolved(transfer)

    return resolved


def notification_item_dict(note: Notification, *, resolved_value: str | None) -> dict:
    action = (note.payload or {}).get("action")
    has_action = isinstance(action, dict) and bool(action.get("type"))
    needs_action = has_action and resolved_value is None
    try:
        group = group_of(note.kind)
    except ValueError:
        group = "account"
    return {
        "id": note.pk,
        "kind": note.kind,
        "group": group,
        "title": note.title,
        "message": note.message,
        "link": note.link,
        "payload": note.payload or {},
        "created_at": note.created_at,
        "read_at": note.read_at,
        "needs_action": needs_action,
        "resolved": resolved_value if has_action else None,
    }


def filter_queryset(user, filter_name: str):
    qs = Notification.objects.filter(user=user).order_by("-created_at", "-id")
    if filter_name == "all":
        return qs
    if filter_name == "payments":
        return qs.filter(kind__in=PAYMENT_KINDS)
    if filter_name == "plans":
        return qs.filter(kind__in=PLAN_KINDS)
    if filter_name == "reminders":
        return qs.filter(kind__in=REMINDER_KINDS)
    return qs


def action_notification_queryset(user):
    return Notification.objects.filter(user=user, payload__has_key="action").order_by(
        "-created_at", "-id"
    )


def notifications_for_action_filter(user) -> list[Notification]:
    candidates = list(action_notification_queryset(user))
    resolved = resolve_for_notifications(candidates)
    return [n for n in candidates if resolved.get(n.pk) is None]


def notification_counts(user) -> tuple[dict[str, int], int]:
    base = Notification.objects.filter(user=user)
    counts = {
        "all": base.count(),
        "payments": base.filter(kind__in=PAYMENT_KINDS).count(),
        "plans": base.filter(kind__in=PLAN_KINDS).count(),
        "reminders": base.filter(kind__in=REMINDER_KINDS).count(),
    }
    unread = base.filter(read_at__isnull=True).count()
    action_candidates = list(action_notification_queryset(user))
    resolved = resolve_for_notifications(action_candidates)
    counts["action"] = sum(1 for n in action_candidates if resolved.get(n.pk) is None)
    return counts, unread


def serialize_page(notifications: list[Notification]) -> list[dict]:
    resolved = resolve_for_notifications(notifications)
    return [notification_item_dict(n, resolved_value=resolved.get(n.pk)) for n in notifications]
