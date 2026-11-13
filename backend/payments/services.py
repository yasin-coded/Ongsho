from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from audit import services as audit_services
from core.choices import PaymentMethod
from core.exceptions import ConflictError, Forbidden, NotFound, ValidationFailed
from core.money import format_bdt, quantize_money
from core.notify import notify, resolve_notifications
from core.validators import normalize_tid, validate_transaction_id
from dues.models import Due, DueStatus
from dues.state import transition
from payments.models import Payment, PaymentAllocation, ReviewStatus
from plans.models import PlanMode, Subscription
from sharing.models import Member, MemberStatus, SharedPlan


def _first_name(user) -> str:
    return ((user.name or "").strip().split(" ") or [""])[0] or (user.name or "")


def _method_label(method: str) -> str:
    return dict(PaymentMethod.choices).get(method, method)


def _owned_payment(user, payment_id: int) -> Payment:
    payment = (
        Payment.objects.select_related(
            "shared_plan",
            "shared_plan__subscription",
            "member",
            "member__user",
        )
        .filter(pk=payment_id, shared_plan__subscription__owner=user)
        .first()
    )
    if payment is None:
        raise NotFound("Not found.")
    return payment


def _owned_due(user, due_id: int) -> Due:
    due = (
        Due.objects.select_related(
            "charge__subscription",
            "member",
            "member__user",
            "member__shared_plan",
        )
        .filter(pk=due_id, charge__subscription__owner=user)
        .first()
    )
    if due is None:
        raise NotFound("Not found.")
    return due


def _payer_member(user, plan_id: int) -> Member:
    if Subscription.objects.filter(pk=plan_id, owner=user, archived_on__isnull=True).exists():
        raise Forbidden("Use mark as paid for your own seat.", code="owner_cannot_submit")
    member = (
        Member.objects.select_related("shared_plan__subscription", "user")
        .filter(
            user=user,
            shared_plan__subscription_id=plan_id,
            shared_plan__subscription__archived_on__isnull=True,
            status__in=(MemberStatus.ACTIVE, MemberStatus.LEAVE_REQUESTED),
        )
        .first()
    )
    if member is None:
        raise NotFound("Not found.")
    return member


def _month_name(charge) -> str:
    return charge.period_start.strftime("%B")


def _covered_months(payment: Payment) -> str:
    names: list[str] = []
    seen: set[str] = set()
    for alloc in payment.allocations.select_related("due__charge").all():
        label = _month_name(alloc.due.charge)
        if label not in seen:
            seen.add(label)
            names.append(label)
    return " and ".join(names)


def _reject_pending_payment(payment: Payment, *, reason: str, actor) -> None:
    if payment.review_status != ReviewStatus.PENDING:
        return
    payment.review_status = ReviewStatus.REJECTED
    payment.reviewed_at = timezone.now()
    payment.save(update_fields=["review_status", "reviewed_at"])
    resolve_notifications("payment", payment_id=payment.pk)
    for alloc in PaymentAllocation.objects.filter(payment=payment).select_related("due"):
        due = alloc.due
        if due.status == DueStatus.PENDING:
            transition(due, DueStatus.DUE, actor, rejection_reason=reason)


def _lock_dues(due_ids: list[int]) -> list[Due]:
    dues = list(
        Due.objects.select_for_update()
        .filter(pk__in=due_ids)
        .select_related("charge", "member", "member__user", "charge__subscription")
    )
    if len(dues) != len(set(due_ids)):
        raise ConflictError("One of those dues is no longer open.", code="due_not_open")
    return dues


@transaction.atomic
def submit_payment(
    user,
    *,
    plan_id: int,
    due_ids: list[int],
    method: str,
    transaction_id: str,
    amount: Decimal | None = None,
    paid_on: date | None = None,
    today: date,
) -> Payment:
    if not due_ids:
        raise ValidationFailed("Pick at least one due.", fields={"due_ids": ["Pick at least one due."]})
    payer = _payer_member(user, plan_id)
    shared = payer.shared_plan
    sub = shared.subscription

    if method not in PaymentMethod.values:
        raise ValidationFailed("Pick a payment method.", fields={"method": ["Pick a payment method."]})
    if paid_on is not None and paid_on > today:
        raise ValidationFailed("The date cannot be in the future.", fields={"paid_on": ["The date cannot be in the future."]})

    tid = validate_transaction_id(transaction_id)
    if Payment.objects.filter(shared_plan=shared, transaction_id=tid).exists():
        raise ValidationFailed(
            "This ID was already used on this plan.",
            fields={"transaction_id": ["This ID was already used on this plan."]},
        )

    dues = _lock_dues(due_ids)
    for due in dues:
        if due.charge.subscription_id != plan_id:
            raise ConflictError("One of those dues is no longer open.", code="due_not_open")
        if due.status != DueStatus.DUE:
            raise ConflictError("One of those dues is no longer open.", code="due_not_open")
    if sub.plan_mode == PlanMode.RESELLER:
        for due in dues:
            if due.member_id != payer.pk:
                raise ConflictError("You can only pay your own dues on this plan.", code="reseller_own_dues_only")

    total = sum((quantize_money(d.amount_bdt) for d in dues), Decimal("0"))
    if amount is not None and quantize_money(amount) != total:
        raise ValidationFailed(
            "The amount must match the selected dues.",
            code="amount_mismatch",
            fields={"amount": ["The amount must match the selected dues."]},
        )

    for due in dues:
        transition(due, DueStatus.PENDING, user, rejection_reason="")

    try:
        payment = Payment.objects.create(
            shared_plan=shared,
            member=payer,
            recorded_by=user,
            method=method,
            transaction_id=tid,
            amount=total,
            paid_on=paid_on,
            review_status=ReviewStatus.PENDING,
        )
    except IntegrityError as exc:
        for due in dues:
            due.refresh_from_db()
            if due.status == DueStatus.PENDING:
                transition(due, DueStatus.DUE, user)
        raise ValidationFailed(
            "This ID was already used on this plan.",
            fields={"transaction_id": ["This ID was already used on this plan."]},
        ) from exc

    for due in dues:
        PaymentAllocation.objects.create(payment=payment, due=due, amount_applied=due.amount_bdt)

    owner = sub.owner
    audit_services.log(
        user,
        "payment.submitted",
        "Payment",
        payment.pk,
        None,
        {"amount": str(total), "transaction_id": tid},
        plan_id=sub.pk,
        summary=f"{_first_name(user)} sent {format_bdt(total)} (ID {tid})",
        amount=total,
    )
    notify(
        owner,
        "payment_submitted",
        f"{_first_name(user)} sent a transaction ID",
        f"{sub.plan_name} · {_method_label(method)} · ID {tid} · {format_bdt(total)}",
        link=f"/app/plans/{sub.pk}/review",
        payload={
            "action": {"type": "payment", "payment_id": payment.pk, "plan_id": sub.pk},
            "plan_id": sub.pk,
        },
    )
    return payment


@transaction.atomic
def confirm_payment(user, payment_id: int) -> dict:
    payment = _owned_payment(user, payment_id)
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.review_status != ReviewStatus.PENDING:
        raise ConflictError("This payment was already decided.", code="already_decided")

    now = timezone.now()
    payment.review_status = ReviewStatus.CONFIRMED
    payment.reviewed_at = now
    payment.save(update_fields=["review_status", "reviewed_at"])

    for alloc in PaymentAllocation.objects.filter(payment=payment).select_related("due"):
        transition(alloc.due, DueStatus.PAID, user)

    sub = payment.shared_plan.subscription
    payer = payment.member.user
    months = _covered_months(payment)
    audit_services.log(
        user,
        "payment.confirmed",
        "Payment",
        payment.pk,
        None,
        {"status": ReviewStatus.CONFIRMED},
        plan_id=sub.pk,
        summary=f"You confirmed {_first_name(payer)}'s payment for {months}",
        amount=payment.amount,
    )
    notify(
        payer,
        "payment_confirmed",
        f"{_first_name(sub.owner)} confirmed your payment",
        f"{sub.plan_name} · {months} · {format_bdt(payment.amount)}",
        link=f"/app/shared/{sub.pk}",
        payload={"plan_id": sub.pk},
    )
    resolve_notifications("payment", payment_id=payment.pk)
    return {"message": f"Payment confirmed. It covered {months}."}


@transaction.atomic
def reject_payment(user, payment_id: int, *, reason: str) -> dict:
    payment = _owned_payment(user, payment_id)
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    clean = (reason or "").strip()
    if not clean:
        raise ValidationFailed(
            "Write a short reason.",
            fields={"reason": ["Write a short reason. The member will see it."]},
        )
    if payment.review_status != ReviewStatus.PENDING:
        raise ConflictError("This payment was already decided.", code="already_decided")

    payment.review_status = ReviewStatus.REJECTED
    payment.reviewed_at = timezone.now()
    payment.save(update_fields=["review_status", "reviewed_at"])

    for alloc in PaymentAllocation.objects.filter(payment=payment).select_related("due"):
        transition(alloc.due, DueStatus.DUE, user, rejection_reason=clean)

    sub = payment.shared_plan.subscription
    payer = payment.member.user
    audit_services.log(
        user,
        "payment.rejected",
        "Payment",
        payment.pk,
        None,
        {"reason": clean},
        plan_id=sub.pk,
        summary=f"You rejected {_first_name(payer)}'s payment",
        amount=payment.amount,
    )
    notify(
        payer,
        "payment_rejected",
        "Payment not confirmed",
        clean,
        link=f"/app/shared/{sub.pk}",
        payload={"plan_id": sub.pk},
    )
    resolve_notifications("payment", payment_id=payment.pk)
    return {
        "message": f"Rejected. {_first_name(payer)}'s due is back to Due, and they can see your reason."
    }


@transaction.atomic
def reverse_payment(user, payment_id: int) -> dict:
    payment = _owned_payment(user, payment_id)
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.review_status != ReviewStatus.CONFIRMED:
        raise ConflictError("Only a confirmed payment can be reversed.", code="only_confirmed")

    allocs = list(PaymentAllocation.objects.filter(payment=payment).select_related("due"))
    if not allocs:
        raise ConflictError("This payment cannot be reversed.", code="cannot_reverse")
    for alloc in allocs:
        if alloc.due.status != DueStatus.PAID:
            raise ConflictError("This payment cannot be reversed.", code="cannot_reverse")
        newer = (
            PaymentAllocation.objects.filter(
                due=alloc.due,
                payment__review_status=ReviewStatus.CONFIRMED,
                payment_id__gt=payment.pk,
            )
            .exists()
        )
        if newer:
            raise ConflictError("This payment cannot be reversed.", code="cannot_reverse")

    payment.review_status = ReviewStatus.REVERSED
    payment.reviewed_at = timezone.now()
    payment.save(update_fields=["review_status", "reviewed_at"])

    sub = payment.shared_plan.subscription
    payer = payment.member.user
    for alloc in allocs:
        transition(alloc.due, DueStatus.DUE, user)

    audit_services.log(
        user,
        "payment.reversed",
        "Payment",
        payment.pk,
        None,
        {"status": ReviewStatus.REVERSED},
        plan_id=sub.pk,
        summary=f"You reversed {_first_name(payer)}'s payment",
        amount=payment.amount,
    )
    notify(
        payer,
        "payment_reversed",
        "Payment reversed",
        f"{sub.plan_name} · {format_bdt(payment.amount)}",
        link=f"/app/shared/{sub.pk}",
        payload={"plan_id": sub.pk},
    )
    return {"message": "Reversed. The original stays in the history, and the due is back to Due."}


@transaction.atomic
def mark_due_paid(user, due_id: int, *, paid_on: date, method: str, note: str, today: date) -> dict:
    due = _owned_due(user, due_id)
    due = Due.objects.select_for_update().get(pk=due.pk)
    if due.status not in (DueStatus.DUE, DueStatus.PENDING):
        raise ConflictError("This due is already Paid.", code="already_paid")
    if paid_on > today:
        raise ValidationFailed("The date cannot be in the future.", fields={"date": ["The date cannot be in the future."]})
    if not paid_on:
        raise ValidationFailed("Pick the date.", fields={"date": ["Pick the date you were paid."]})
    if method not in PaymentMethod.values:
        raise ValidationFailed("Pick how you were paid.", fields={"method": ["Pick how you were paid."]})

    sub = due.charge.subscription
    shared = due.member.shared_plan
    member_user = due.member.user
    is_owner_seat = sub.owner_id == member_user.pk

    pending = PaymentAllocation.objects.filter(
        due=due, payment__review_status=ReviewStatus.PENDING
    ).select_related("payment").first()
    if pending:
        _reject_pending_payment(
            pending.payment,
            reason="The owner recorded this due as paid.",
            actor=user,
        )

    if due.status == DueStatus.PENDING:
        due.refresh_from_db()

    now = timezone.now()
    payment = Payment.objects.create(
        shared_plan=shared,
        member=due.member,
        recorded_by=user,
        method=method,
        transaction_id=None,
        amount=due.amount_bdt,
        paid_on=paid_on,
        review_status=ReviewStatus.CONFIRMED,
        reviewed_at=now,
        note=(note or "").strip(),
    )
    PaymentAllocation.objects.create(payment=payment, due=due, amount_applied=due.amount_bdt)
    transition(due, DueStatus.PAID, user)

    month = _month_name(due.charge)
    audit_services.log(
        user,
        "due.mark_paid",
        "Due",
        due.pk,
        None,
        {"status": DueStatus.PAID},
        plan_id=sub.pk,
        summary=f"You marked {_first_name(member_user)}'s {month} due as paid",
        amount=due.amount_bdt,
    )
    if not is_owner_seat:
        notify(
            member_user,
            "payment_recorded",
            f"{_first_name(sub.owner)} marked {month} as paid",
            f"{sub.plan_name} · {format_bdt(due.amount_bdt)} · recorded by the owner",
            link=f"/app/shared/{sub.pk}",
            payload={"plan_id": sub.pk},
        )
    return {
        "message": f"Marked as Paid (recorded by owner). {_first_name(member_user)} is told."
    }


@transaction.atomic
def waive_due(user, due_id: int, *, note: str) -> dict:
    due = _owned_due(user, due_id)
    due = Due.objects.select_for_update().get(pk=due.pk)
    clean = (note or "").strip()
    if not clean:
        raise ValidationFailed("Add a short note.", fields={"note": ["Add a short note."]})
    if due.status not in (DueStatus.DUE, DueStatus.PENDING):
        raise ConflictError("This due cannot be waived.", code="already_paid")

    sub = due.charge.subscription
    member_user = due.member.user

    pending_alloc = PaymentAllocation.objects.filter(
        due=due, payment__review_status=ReviewStatus.PENDING
    ).select_related("payment").first()
    if pending_alloc:
        payment_pending = pending_alloc.payment
        payment = Payment.objects.select_for_update().get(pk=payment_pending.pk)
        payment.review_status = ReviewStatus.REJECTED
        payment.reviewed_at = timezone.now()
        payment.save(update_fields=["review_status", "reviewed_at"])
        resolve_notifications("payment", payment_id=payment.pk)
        for alloc in PaymentAllocation.objects.filter(payment=payment).select_related("due"):
            if alloc.due_id == due.pk:
                continue
            other = alloc.due
            if other.status == DueStatus.PENDING:
                transition(
                    other,
                    DueStatus.DUE,
                    user,
                    rejection_reason="The owner waived another due in this payment. Send the rest again.",
                )
        due.refresh_from_db()

    transition(due, DueStatus.WAIVED, user, waiver_note=clean)
    month = _month_name(due.charge)
    audit_services.log(
        user,
        "due.waived",
        "Due",
        due.pk,
        None,
        {"status": DueStatus.WAIVED, "note": clean},
        plan_id=sub.pk,
        summary=f"You waived {_first_name(member_user)}'s due: {clean}",
        amount=due.amount_bdt,
    )
    if sub.owner_id != member_user.pk:
        notify(
            member_user,
            "due_waived",
            f"{_first_name(sub.owner)} waived {month}",
            clean,
            link=f"/app/shared/{sub.pk}",
            payload={"plan_id": sub.pk},
        )
    if pending_alloc:
        resolve_notifications("payment", payment_id=pending_alloc.payment_id)
    return {"message": "Waived. Nothing is owed for that due now."}


@transaction.atomic
def waive_payment(user, payment_id: int, *, note: str) -> dict:
    payment = _owned_payment(user, payment_id)
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    clean = (note or "").strip()
    if not clean:
        raise ValidationFailed("Add a short note.", fields={"note": ["Add a short note."]})
    if payment.review_status != ReviewStatus.PENDING:
        raise ConflictError("This payment was already decided.", code="already_decided")

    sub = payment.shared_plan.subscription
    payer = payment.member.user
    months = _covered_months(payment)

    for alloc in PaymentAllocation.objects.filter(payment=payment).select_related("due"):
        due = Due.objects.select_for_update().get(pk=alloc.due.pk)
        if due.status == DueStatus.PENDING:
            transition(due, DueStatus.WAIVED, user, waiver_note=clean)

    payment.review_status = ReviewStatus.REJECTED
    payment.reviewed_at = timezone.now()
    payment.save(update_fields=["review_status", "reviewed_at"])

    audit_services.log(
        user,
        "payment.waived",
        "Payment",
        payment.pk,
        None,
        {"note": clean},
        plan_id=sub.pk,
        summary=f"You waived {_first_name(payer)}'s payment: {clean}",
        amount=payment.amount,
    )
    notify(
        payer,
        "due_waived",
        f"{_first_name(sub.owner)} waived {months}",
        clean,
        link=f"/app/shared/{sub.pk}",
        payload={"plan_id": sub.pk},
    )
    resolve_notifications("payment", payment_id=payment.pk)
    return {"message": "Waived. Nothing is owed for those dues now."}


@transaction.atomic
def set_due_back(user, due_id: int) -> dict:
    due = _owned_due(user, due_id)
    due = Due.objects.select_for_update().get(pk=due.pk)
    sub = due.charge.subscription
    member_user = due.member.user
    is_owner_seat = sub.owner_id == member_user.pk

    if due.status == DueStatus.PENDING:
        raise ConflictError("Reject or confirm the pending payment first.", code="already_decided")

    if due.status == DueStatus.PAID:
        confirmed = PaymentAllocation.objects.filter(
            due=due, payment__review_status=ReviewStatus.CONFIRMED
        ).select_related("payment")
        alloc = confirmed.order_by("-payment_id").first()
        if alloc is None:
            transition(due, DueStatus.DUE, user)
        else:
            pay = alloc.payment
            multi = pay.allocations.count() > 1
            if multi:
                raise ConflictError("Use reverse on the payment instead.", code="use_reverse")
            pay.review_status = ReviewStatus.REVERSED
            pay.reviewed_at = timezone.now()
            pay.save(update_fields=["review_status", "reviewed_at"])
            transition(due, DueStatus.DUE, user)
    elif due.status == DueStatus.WAIVED:
        transition(due, DueStatus.DUE, user)
    else:
        raise ConflictError("This due is already Due.", code="already_paid")

    month = _month_name(due.charge)
    audit_services.log(
        user,
        "due.set_due",
        "Due",
        due.pk,
        None,
        {"status": DueStatus.DUE},
        plan_id=sub.pk,
        summary=f"You set {_first_name(member_user)}'s {month} back to Due",
        amount=due.amount_bdt,
    )
    if not is_owner_seat:
        notify(
            member_user,
            "payment_reversed",
            f"{_first_name(sub.owner)} set {month} back to Due",
            sub.plan_name,
            link=f"/app/shared/{sub.pk}",
            payload={"plan_id": sub.pk},
        )
    return {"message": "Set back to Due."}


def submit_message(payment: Payment) -> str:
    owner_name = _first_name(payment.shared_plan.subscription.owner)
    return f"Sent. {owner_name} will confirm it. Until then your due shows Pending."
