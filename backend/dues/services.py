from __future__ import annotations

from decimal import Decimal

from django.apps import apps
from django.db import transaction
from django.db.models import Q

from audit import services as audit_services
from billing.models import Charge
from core.money import format_bdt, quantize_money
from core.notify import notify
from dues.models import Due, DueStatus
from dues.splitting import members_for_charge, split_charge
from dues.state import transition
from plans.models import PlanMode
from sharing.models import Member, SharedPlan


def _shared_for_charge(charge: Charge) -> SharedPlan | None:
    return SharedPlan.objects.filter(subscription_id=charge.subscription_id).select_related("subscription").first()


def _is_owner_seat(member: Member) -> bool:
    sub = member.shared_plan.subscription
    return sub.plan_mode == PlanMode.OWNER and member.user_id == sub.owner_id


def _month_label(charge: Charge) -> str:
    return charge.period_start.strftime("%B %Y")


def _split_blocked_notified(charge: Charge) -> bool:
    Notification = apps.get_model("notifications", "Notification")
    return Notification.objects.filter(
        kind="split_blocked",
        payload__charge_id=charge.pk,
    ).exists()


@transaction.atomic
def create_dues_for_charge(charge: Charge) -> int:
    shared = _shared_for_charge(charge)
    if shared is None:
        return 0
    members = members_for_charge(shared, charge)
    if not members:
        return 0
    result = split_charge(shared, members, charge.amount_bdt)
    if not result.ok:
        if not _split_blocked_notified(charge):
            sub = shared.subscription
            month = _month_label(charge)
            title = f"Fix the split for {sub.plan_name}"
            message = f"{sub.plan_name} · the amounts for {month} do not add up to the charge"
            notify(
                sub.owner,
                "split_blocked",
                title,
                message,
                link=f"/app/plans/{sub.pk}",
                payload={"charge_id": charge.pk, "plan_id": sub.pk},
            )
            audit_services.log(
                sub.owner,
                "due.split_blocked",
                "Charge",
                charge.pk,
                None,
                {"blocked": True, "reason": result.reason},
                plan_id=sub.pk,
                summary="",
            )
        return 0

    created = 0
    for member, amount in zip(members, result.amounts, strict=True):
        _, was_new = Due.objects.get_or_create(
            charge=charge,
            member=member,
            defaults={"amount_bdt": amount, "status": DueStatus.DUE},
        )
        if was_new:
            created += 1
    return created


def _charge_unlocked(charge: Charge, today) -> bool:
    return not charge.locked or charge.due_date > today


@transaction.atomic
def recalculate_dues(charge: Charge, today, *, force: bool = False) -> None:
    if not force and charge.locked:
        shared = _shared_for_charge(charge)
        if shared is None:
            return
        members = members_for_charge(shared, charge)
        result = split_charge(shared, members, charge.amount_bdt)
        if result.ok and not Due.objects.filter(charge=charge).exists():
            create_dues_for_charge(charge)
        return
    shared = _shared_for_charge(charge)
    if shared is None:
        return
    members = members_for_charge(shared, charge)
    existing = {d.member_id: d for d in Due.objects.filter(charge=charge).select_related("member", "member__user")}
    member_ids = {m.pk for m in members}

    result = split_charge(shared, members, charge.amount_bdt)
    if not result.ok:
        if not existing and not _split_blocked_notified(charge):
            create_dues_for_charge(charge)
        return

    if not existing:
        create_dues_for_charge(charge)
        return

    amounts_by_member = {m.pk: amt for m, amt in zip(members, result.amounts, strict=True)}

    for member_id, due in list(existing.items()):
        if member_id not in member_ids:
            if due.status == DueStatus.DUE:
                due.delete()
            continue
        new_amount = amounts_by_member[member_id]
        if due.status == DueStatus.DUE:
            if due.amount_bdt != new_amount:
                old_amt = due.amount_bdt
                due.amount_bdt = new_amount
                due.save(update_fields=["amount_bdt"])
                sub = shared.subscription
                notify(
                    due.member.user,
                    "amount_changed",
                    f"Your {sub.plan_name} share changed",
                    f"{_month_label(charge)} is now {format_bdt(new_amount)}. It was {format_bdt(old_amt)}.",
                    link=f"/app/shared/{sub.pk}",
                    payload={"plan_id": sub.pk, "charge_id": charge.pk},
                )
        elif due.status == DueStatus.PAID and _is_owner_seat(due.member):
            if due.amount_bdt != new_amount:
                due.amount_bdt = new_amount
                due.save(update_fields=["amount_bdt"])

    for member in members:
        if member.pk not in existing:
            Due.objects.create(
                charge=charge,
                member=member,
                amount_bdt=amounts_by_member[member.pk],
                status=DueStatus.DUE,
            )


def recalculate_plan_dues(plan, today, *, force: bool = False) -> None:
    for charge in Charge.objects.filter(subscription=plan).order_by("period_start"):
        if force or _charge_unlocked(charge, today):
            recalculate_dues(charge, today, force=force)


def unlocked_charges_for_plan(plan, today):
    return Charge.objects.filter(subscription=plan).filter(Q(locked=False) | Q(due_date__gt=today))


@transaction.atomic
def apply_leave_unpaid(member: Member, *, today, unpaid: str, actor) -> None:
    if unpaid != "waive":
        return
    for due in Due.objects.filter(
        member=member,
        status=DueStatus.DUE,
        charge__subscription=member.shared_plan.subscription,
        charge__due_date__lte=today,
    ):
        transition(due, DueStatus.WAIVED, actor, waiver_note="Waived when you left")


@transaction.atomic
@transaction.atomic
def adjust_dues_after_ownership_transfer(shared: SharedPlan, old_owner, new_owner, today, *, actor) -> None:
    from payments.models import PaymentAllocation

    old_member = Member.objects.filter(shared_plan=shared, user=old_owner).first()
    new_member = Member.objects.filter(shared_plan=shared, user=new_owner).first()
    if old_member is None or new_member is None:
        return
    charges = Charge.objects.filter(subscription=shared.subscription, due_date__gt=today)
    for charge in charges:
        if charge.locked:
            continue
        old_due = Due.objects.filter(charge=charge, member=old_member).first()
        if old_due and old_due.status == DueStatus.PAID and not PaymentAllocation.objects.filter(due=old_due).exists():
            transition(old_due, DueStatus.DUE, actor)
        new_due = Due.objects.filter(charge=charge, member=new_member).first()
        if new_due and new_due.status == DueStatus.DUE:
            transition(new_due, DueStatus.PAID, actor)


def ensure_dues(today) -> int:
    touched = 0
    for shared in SharedPlan.objects.filter(subscription__archived_on__isnull=True).select_related("subscription"):
        sub = shared.subscription
        for charge in Charge.objects.filter(subscription=sub):
            eligible = members_for_charge(shared, charge)
            if not eligible:
                continue
            have = set(Due.objects.filter(charge=charge).values_list("member_id", flat=True))
            need = {m.pk for m in eligible}
            if need - have or (not have and need):
                before = Due.objects.filter(charge=charge).count()
                create_dues_for_charge(charge)
                after = Due.objects.filter(charge=charge).count()
                if after > before:
                    touched += 1
    return touched
