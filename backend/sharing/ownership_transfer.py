"""Ownership transfer lifecycle (Owner mode shared plans)."""

from __future__ import annotations

from datetime import date

from django.db import transaction

from accounts import services as account_services
from audit import services as audit_services
from core.exceptions import ConflictError, NotFound, ValidationFailed
from core.notify import notify, resolve_notifications
from core.signals import ownership_transferred
from plans.models import PlanMode, Subscription
from sharing.models import Member, MemberStatus, OwnershipTransfer, SharedPlan, TransferStatus


def _first_name(user) -> str:
    from sharing import services as sharing_services

    return sharing_services._first_name(user)


def _audit(user, action: str, entity_id: int, summary: str, *, plan_id: int) -> None:
    audit_services.log(user, action, "OwnershipTransfer", entity_id, None, None, plan_id=plan_id, summary=summary)


def _shared_for_owner(user, plan_id: int) -> SharedPlan:
    shared = (
        SharedPlan.objects.select_related("subscription")
        .filter(subscription__owner=user, subscription_id=plan_id, subscription__archived_on__isnull=True)
        .first()
    )
    if shared is None:
        raise NotFound("Plan not found.")
    return shared


def _pending_for_plan(shared: SharedPlan) -> OwnershipTransfer | None:
    return OwnershipTransfer.objects.filter(shared_plan=shared, status=TransferStatus.PENDING).first()


def _transfer_for_from_user(user, transfer_id: int) -> OwnershipTransfer:
    transfer = (
        OwnershipTransfer.objects.select_related("shared_plan__subscription", "from_user", "to_user")
        .filter(pk=transfer_id, from_user=user)
        .first()
    )
    if transfer is None:
        raise NotFound("Not found.")
    sub = transfer.shared_plan.subscription
    if sub.owner_id != user.pk:
        raise NotFound("Not found.")
    return transfer


def _transfer_for_to_user(user, transfer_id: int) -> OwnershipTransfer:
    transfer = (
        OwnershipTransfer.objects.select_related("shared_plan__subscription", "from_user", "to_user")
        .filter(pk=transfer_id, to_user=user)
        .first()
    )
    if transfer is None:
        raise NotFound("Not found.")
    return transfer


def _require_pending(transfer: OwnershipTransfer) -> None:
    if transfer.status != TransferStatus.PENDING:
        raise ConflictError("This transfer is no longer open.", code="transfer_closed")


def _target_member(shared: SharedPlan, member_id: int) -> Member:
    member = (
        Member.objects.select_related("user")
        .filter(pk=member_id, shared_plan=shared)
        .first()
    )
    if member is None or member.status == MemberStatus.LEFT:
        raise ValidationFailed(
            "Pick a member who is still on the plan.",
            code="validation_failed",
            fields={"member_id": ["Pick a member who is still on the plan."]},
        )
    if member.status != MemberStatus.ACTIVE:
        raise ValidationFailed(
            "Pick an active member.",
            code="validation_failed",
            fields={"member_id": ["Pick an active member."]},
        )
    if member.user_id == shared.subscription.owner_id:
        raise ValidationFailed(
            "You cannot transfer to the owner seat.",
            code="validation_failed",
            fields={"member_id": ["Pick a member who is not the owner."]},
        )
    return member


@transaction.atomic
def start_ownership_transfer(user, plan_id: int, *, member_id: int, password: str) -> OwnershipTransfer:
    shared = _shared_for_owner(user, plan_id)
    sub = shared.subscription
    if sub.plan_mode == PlanMode.RESELLER:
        raise ValidationFailed("Reseller plans cannot change owner.", code="transfer_not_allowed")
    account_services.verify_current_password(user, password)
    member = _target_member(shared, member_id)
    if _pending_for_plan(shared) is not None:
        raise ConflictError("A transfer is already waiting.", code="transfer_exists")
    transfer = OwnershipTransfer.objects.create(
        shared_plan=shared,
        from_user=user,
        to_user=member.user,
        status=TransferStatus.PENDING,
    )
    plan_name = sub.plan_name
    notify(
        member.user,
        "transfer",
        f"{_first_name(user)} wants you to own {plan_name}",
        "Accept to take over paying the provider. All history moves with the plan, and nothing changes until you accept.",
        link=f"/app/shared/{sub.pk}",
        payload={
            "action": {"type": "transfer", "transfer_id": transfer.pk, "plan_id": sub.pk},
            "plan_id": sub.pk,
        },
    )
    _audit(
        user,
        "transfer.started",
        transfer.pk,
        f"You asked {_first_name(member.user)} to take over {plan_name}",
        plan_id=sub.pk,
    )
    return transfer


@transaction.atomic
def cancel_ownership_transfer(user, transfer_id: int) -> OwnershipTransfer:
    transfer = OwnershipTransfer.objects.select_for_update().select_related(
        "shared_plan__subscription", "from_user", "to_user"
    ).get(pk=_transfer_for_from_user(user, transfer_id).pk)
    _require_pending(transfer)
    transfer.status = TransferStatus.CANCELLED
    transfer.save(update_fields=["status"])
    sub = transfer.shared_plan.subscription
    resolve_notifications("transfer", transfer_id=transfer.pk)
    notify(
        transfer.to_user,
        "transfer_result",
        f"{_first_name(user)} cancelled the transfer",
        sub.plan_name,
        link=f"/app/shared/{sub.pk}",
        payload={"plan_id": sub.pk},
    )
    _audit(
        user,
        "transfer.cancelled",
        transfer.pk,
        f"You cancelled the transfer of {sub.plan_name}",
        plan_id=sub.pk,
    )
    return transfer


@transaction.atomic
def decline_ownership_transfer(user, transfer_id: int) -> OwnershipTransfer:
    transfer = OwnershipTransfer.objects.select_for_update().select_related(
        "shared_plan__subscription", "from_user", "to_user"
    ).get(pk=_transfer_for_to_user(user, transfer_id).pk)
    _require_pending(transfer)
    transfer.status = TransferStatus.DECLINED
    transfer.save(update_fields=["status"])
    sub = transfer.shared_plan.subscription
    resolve_notifications("transfer", transfer_id=transfer.pk)
    notify(
        transfer.from_user,
        "transfer_result",
        f"{_first_name(user)} declined to take over {sub.plan_name}",
        "Nothing changed.",
        link=f"/app/plans/{sub.pk}",
        payload={"plan_id": sub.pk},
    )
    _audit(
        user,
        "transfer.declined",
        transfer.pk,
        f"{user.name} declined to take over {sub.plan_name}",
        plan_id=sub.pk,
    )
    return transfer


@transaction.atomic
def accept_ownership_transfer(user, transfer_id: int, *, today: date) -> dict:
    transfer = (
        OwnershipTransfer.objects.select_for_update()
        .select_related("shared_plan__subscription", "from_user", "to_user")
        .filter(pk=transfer_id, to_user=user)
        .first()
    )
    if transfer is None:
        raise NotFound("Not found.")
    _require_pending(transfer)
    shared = SharedPlan.objects.select_for_update().get(pk=transfer.shared_plan_id)
    sub = Subscription.all_with_archived.select_for_update().get(pk=shared.subscription_id)
    if sub.archived_on is not None:
        raise ConflictError("This plan is no longer available.", code="transfer_closed")
    if sub.plan_mode != PlanMode.OWNER:
        raise ConflictError("This plan is no longer available.", code="transfer_closed")
    if sub.owner_id != transfer.from_user_id:
        raise ConflictError("The plan owner changed.", code="owner_changed")
    target = (
        Member.objects.select_for_update()
        .filter(shared_plan=shared, user=user, status=MemberStatus.ACTIVE)
        .first()
    )
    if target is None:
        raise ConflictError("You are no longer a member of this plan.", code="not_a_member")
    old_owner = transfer.from_user
    sub.owner = user
    sub.save(update_fields=["owner"])
    transfer.status = TransferStatus.ACCEPTED
    transfer.save(update_fields=["status"])
    resolve_notifications("transfer", transfer_id=transfer.pk)
    plan_name = sub.plan_name
    notify(
        old_owner,
        "transfer_result",
        f"{_first_name(user)} is now the owner of {plan_name}",
        "You are now a member. All history moved with the plan.",
        link=f"/app/shared/{sub.pk}",
        payload={"plan_id": sub.pk},
    )
    _audit(
        user,
        "transfer.accepted",
        transfer.pk,
        f"{_first_name(user)} became the owner. {_first_name(old_owner)} is now a member.",
        plan_id=sub.pk,
    )
    ownership_transferred.send(
        sender=type(transfer),
        plan=sub,
        old_owner=old_owner,
        new_owner=user,
        today=today,
    )
    return {
        "plan_id": sub.pk,
        "message": f"You now own {plan_name}. It moved to My Plans with all its history.",
    }


@transaction.atomic
def cancel_pending_transfers_for_deleted_plan(shared: SharedPlan, *, actor, plan_name: str) -> int:
    pending = list(
        OwnershipTransfer.objects.select_for_update()
        .filter(shared_plan=shared, status=TransferStatus.PENDING)
        .select_related("to_user")
    )
    if not pending:
        return 0
    plan_id = shared.subscription_id
    for transfer in pending:
        transfer.status = TransferStatus.CANCELLED
        transfer.save(update_fields=["status"])
        resolve_notifications("transfer", transfer_id=transfer.pk)
        notify(
            transfer.to_user,
            "transfer_result",
            f"{_first_name(actor)} cancelled the transfer",
            plan_name,
            link="/app/shared-plans",
            payload={"plan_id": plan_id},
        )
        _audit(
            actor,
            "transfer.cancelled",
            transfer.pk,
            f"Transfer cancelled because {plan_name} was removed",
            plan_id=plan_id,
        )
    return len(pending)
