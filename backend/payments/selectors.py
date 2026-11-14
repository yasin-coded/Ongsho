"""Read-only, user-scoped queries for payments, balances, and IOUs."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Prefetch

from audit.models import AuditLog
from core.exceptions import ValidationFailed
from core.money import quantize_money
from dues.models import Due, DueStatus
from dues import selectors as dues_selectors
from payments.models import Payment, PaymentAllocation, ReviewStatus
from plans.models import PlanMode, Subscription
from plans import selectors as plan_selectors
from sharing import selectors as sharing_selectors
from sharing.models import Member, MemberStatus, SharedPlan

_REVIEW_RANK = {
    ReviewStatus.CONFIRMED: 3,
    ReviewStatus.PENDING: 2,
    ReviewStatus.REJECTED: 1,
    ReviewStatus.REVERSED: 0,
}


def _first_name(user) -> str:
    return ((user.name or "").strip().split(" ") or [""])[0] or (user.name or "")


def _month_label(charge) -> str:
    return charge.period_start.strftime("%Y-%m")


def settling_allocations_for_dues(due_ids: list[int]) -> dict[int, PaymentAllocation]:
    if not due_ids:
        return {}
    by_due: dict[int, PaymentAllocation] = {}
    qs = PaymentAllocation.objects.filter(due_id__in=due_ids).select_related(
        "payment",
        "payment__member__user",
        "payment__recorded_by",
        "due__member",
    )
    for alloc in qs:
        cur = by_due.get(alloc.due_id)
        if cur is None or _REVIEW_RANK[alloc.payment.review_status] > _REVIEW_RANK[cur.payment.review_status]:
            by_due[alloc.due_id] = alloc
    return by_due


def _paid_on(payment: Payment | None) -> str | None:
    if payment is None:
        return None
    if payment.paid_on:
        return payment.paid_on.isoformat()
    if payment.reviewed_at:
        return payment.reviewed_at.date().isoformat()
    return None


def _recorded_by_owner(payment: Payment | None) -> bool:
    if payment is None:
        return False
    return payment.recorded_by_id != payment.member.user_id


def plan_dues_for_ledger(shared: SharedPlan) -> list[Due]:
    return list(
        Due.objects.filter(charge__subscription_id=shared.subscription_id)
        .select_related("charge", "member__user", "member__shared_plan__subscription")
        .order_by("-charge__due_date", "-id", "member_id")
    )


def parse_ledger_params(request) -> dict:
    params: dict = {}
    member_raw = request.query_params.get("member")
    if member_raw not in (None, ""):
        try:
            params["member"] = int(member_raw)
        except ValueError:
            raise ValidationFailed("Invalid member.", fields={"member": ["Invalid member."]})
    month_raw = request.query_params.get("month")
    if month_raw not in (None, ""):
        try:
            parts = month_raw.split("-")
            year, month = int(parts[0]), int(parts[1])
            if not (1 <= month <= 12):
                raise ValueError
            params["month"] = date(year, month, 1)
        except (ValueError, IndexError):
            raise ValidationFailed("Invalid month.", fields={"month": ["Use YYYY-MM."]})
    status_raw = request.query_params.get("status")
    if status_raw not in (None, ""):
        allowed = {c.value for c in DueStatus}
        if status_raw not in allowed:
            raise ValidationFailed("Invalid status.", fields={"status": ["Invalid status."]})
        params["status"] = status_raw
    return params


def _ledger_row(due: Due, alloc: PaymentAllocation | None, shared: SharedPlan) -> dict:
    payment = alloc.payment if alloc else None
    covered_by = None
    if payment and payment.member_id != due.member_id:
        covered_by = _first_name(payment.member.user)
    sub = shared.subscription
    return {
        "due_id": due.pk,
        "charge_id": due.charge_id,
        "month": _month_label(due.charge),
        "due_date": due.charge.due_date.isoformat(),
        "member": {
            "id": due.member_id,
            "name": due.member.user.name,
            "first_name": _first_name(due.member.user),
            "is_owner_seat": due.member.user_id == sub.owner_id,
        },
        "amount": str(quantize_money(due.amount_bdt)),
        "status": due.status,
        "method": payment.method if payment else None,
        "transaction_id": payment.transaction_id if payment else None,
        "paid_on": _paid_on(payment),
        "recorded_by_owner": _recorded_by_owner(payment),
        "covered_by": covered_by,
        "payment_id": payment.pk if payment else None,
    }


def ledger_build(shared: SharedPlan, params: dict) -> tuple[list[dict], list[dict]]:
    """Return (all_rows_unfiltered, filtered_rows) for meta and pagination."""
    dues = plan_dues_for_ledger(shared)
    alloc_map = settling_allocations_for_dues([d.pk for d in dues])
    member_ids = {m.pk for m in Member.objects.filter(shared_plan=shared)}
    if mid := params.get("member"):
        if mid not in member_ids:
            raise ValidationFailed("Invalid member.", fields={"member": ["Invalid member."]})
    rows = [_ledger_row(d, alloc_map.get(d.pk), shared) for d in dues]
    filtered = rows
    if mid := params.get("member"):
        filtered = [r for r in filtered if r["member"]["id"] == mid]
    if month := params.get("month"):
        key = month.strftime("%Y-%m")
        filtered = [r for r in filtered if r["month"] == key]
    if status := params.get("status"):
        filtered = [r for r in filtered if r["status"] == status]
    return rows, filtered


def ledger_totals(filtered: list[dict]) -> dict:
    totals = {k: Decimal("0") for k in ("paid", "pending", "due", "waived", "all")}
    for row in filtered:
        amt = Decimal(row["amount"])
        totals["all"] += amt
        st = row["status"]
        if st in totals:
            totals[st] += amt
    return {k: str(quantize_money(v)) for k, v in totals.items()}


def ledger_months(all_rows: list[dict]) -> list[dict]:
    seen: dict[str, str] = {}
    for row in all_rows:
        key = row["month"]
        if key not in seen:
            seen[key] = row["due_date"]
    return [
        {"key": k, "label": date.fromisoformat(v[:10]).strftime("%B %Y")}
        for k, v in sorted(seen.items(), reverse=True)
    ]


def ledger_people(all_rows: list[dict]) -> list[dict]:
    people: dict[int, dict] = {}
    for row in all_rows:
        mid = row["member"]["id"]
        if mid not in people:
            people[mid] = {"id": mid, "name": row["member"]["first_name"]}
    return sorted(people.values(), key=lambda x: x["name"].lower())


def plan_ious_owner(shared: SharedPlan) -> list[dict]:
    sub = shared.subscription
    if sub.plan_mode == PlanMode.RESELLER:
        return []
    return _netted_ious(shared)


def plan_ious_member(shared: SharedPlan, viewer: Member) -> list[dict]:
    sub = shared.subscription
    if sub.plan_mode == PlanMode.RESELLER:
        return []
    owner_pairs = _netted_ious(shared)
    viewer_user_id = viewer.user_id
    out = []
    members_by_id = {m.pk: m for m in Member.objects.filter(shared_plan=shared).select_related("user")}
    for row in owner_pairs:
        debtor_m = members_by_id.get(row["debtor"]["id"])
        creditor_m = members_by_id.get(row["creditor"]["id"])
        if debtor_m is None or creditor_m is None:
            continue
        if viewer_user_id not in (debtor_m.user_id, creditor_m.user_id):
            continue
        if viewer_user_id == debtor_m.user_id:
            other = creditor_m.user
            you_owe = True
        else:
            other = debtor_m.user
            you_owe = False
        out.append(
            {
                "other": {
                    "name": other.name,
                    "first_name": _first_name(other),
                    "avatar_id": other.avatar_id,
                },
                "amount": row["amount"],
                "you_owe": you_owe,
            }
        )
    return out


def _netted_ious(shared: SharedPlan) -> list[dict]:
    members = list(Member.objects.filter(shared_plan=shared).select_related("user"))
    user_to_member = {m.user_id: m for m in members}
    pairs: dict[tuple[int, int], Decimal] = defaultdict(lambda: Decimal("0"))
    allocs = (
        PaymentAllocation.objects.filter(
            payment__shared_plan=shared,
            payment__review_status=ReviewStatus.CONFIRMED,
        )
        .select_related("payment__member", "due__member__user")
    )
    for alloc in allocs:
        payer = alloc.payment.member_id
        debtor = alloc.due.member_id
        if payer == debtor:
            continue
        debtor_u = alloc.due.member.user_id
        creditor_u = alloc.payment.member.user_id
        a, b = sorted((debtor_u, creditor_u))
        sign = 1 if debtor_u < creditor_u else -1
        pairs[(a, b)] += sign * alloc.amount_applied

    out = []
    for (a, b), value in pairs.items():
        if value == 0:
            continue
        if value > 0:
            debtor_u, creditor_u = a, b
        else:
            debtor_u, creditor_u = b, a
            value = -value
        debtor_m = user_to_member.get(debtor_u)
        creditor_m = user_to_member.get(creditor_u)
        if debtor_m is None or creditor_m is None:
            continue
        out.append(
            {
                "debtor": {
                    "id": debtor_m.pk,
                    "name": debtor_m.user.name,
                    "first_name": _first_name(debtor_m.user),
                },
                "creditor": {
                    "id": creditor_m.pk,
                    "name": creditor_m.user.name,
                    "first_name": _first_name(creditor_m.user),
                },
                "amount": str(quantize_money(value)),
            }
        )
    out.sort(key=lambda r: (r["debtor"]["name"], r["creditor"]["name"]))
    return out


def _audit_tone(action: str) -> str:
    if action == "payment.submitted":
        return "pending"
    if action in ("payment.confirmed", "due.mark_paid"):
        return "paid"
    if action in (
        "payment.reversed",
        "due.set_due",
        "payment.rejected",
        "member.leave_approved",
    ):
        return "due"
    return "info"


def plan_activity(plan_id: int) -> list[dict]:
    qs = (
        AuditLog.objects.filter(plan_id=plan_id)
        .exclude(summary="")
        .order_by("-created_at", "-id")[:10]
    )
    return [
        {
            "id": row.pk,
            "created_at": row.created_at.isoformat(),
            "text": row.summary,
            "amount": str(quantize_money(row.amount)) if row.amount is not None else None,
            "tone": _audit_tone(row.action),
        }
        for row in qs
    ]


def review_data(shared: SharedPlan, today: date) -> dict:
    sub = shared.subscription
    charge = dues_selectors.current_charge(sub, today)
    if charge is None:
        return _empty_review(sub)

    dues = list(
        Due.objects.filter(charge=charge)
        .select_related("member__user", "charge")
        .order_by("member_id")
    )
    owner_id = sub.owner_id
    member_dues = [d for d in dues if d.member.user_id != owner_id]

    pending_payments = list(
        Payment.objects.filter(shared_plan=shared, review_status=ReviewStatus.PENDING)
        .select_related("member__user")
        .prefetch_related(
            Prefetch(
                "allocations",
                queryset=PaymentAllocation.objects.select_related(
                    "due__member__user", "due__charge"
                ),
            )
        )
        .order_by("-submitted_at", "-id")
    )
    pending = []
    waiting_total = Decimal("0")
    for pay in pending_payments:
        covers = []
        is_iou = False
        for alloc in pay.allocations.all():
            due = alloc.due
            covers.append(
                {
                    "due_id": due.pk,
                    "member_id": due.member_id,
                    "member_first_name": _first_name(due.member.user),
                    "month": _month_label(due.charge),
                    "amount": str(quantize_money(alloc.amount_applied)),
                    "is_payer": due.member_id == pay.member_id,
                }
            )
            if due.member_id != pay.member_id:
                is_iou = True
        waiting_total += pay.amount
        payer = pay.member
        pending.append(
            {
                "payment_id": pay.pk,
                "payer": {
                    "id": payer.pk,
                    "name": payer.user.name,
                    "first_name": _first_name(payer.user),
                    "email": payer.user.email,
                    "avatar_id": payer.user.avatar_id,
                    "leave_requested": payer.status == MemberStatus.LEAVE_REQUESTED,
                },
                "method": pay.method,
                "transaction_id": pay.transaction_id,
                "amount": str(quantize_money(pay.amount)),
                "submitted_at": pay.submitted_at.isoformat() if pay.submitted_at else None,
                "covers": covers,
                "is_iou": is_iou,
            }
        )

    alloc_map = settling_allocations_for_dues([d.pk for d in dues])
    decided = []
    for due in dues:
        if due.status not in (DueStatus.PAID, DueStatus.WAIVED):
            continue
        alloc = alloc_map.get(due.pk)
        payment = alloc.payment if alloc else None
        decided.append(
            {
                "due_id": due.pk,
                "payment_id": payment.pk if payment else None,
                "member": {
                    "id": due.member_id,
                    "first_name": _first_name(due.member.user),
                    "email": due.member.user.email,
                    "avatar_id": due.member.user.avatar_id,
                    "leave_requested": due.member.status == MemberStatus.LEAVE_REQUESTED,
                    "is_owner_seat": sharing_selectors.is_owner_seat(due.member),
                },
                "status": due.status,
                "amount": str(quantize_money(due.amount_bdt)),
                "waiver_note": due.waiver_note or None,
                "method": payment.method if payment else None,
                "transaction_id": payment.transaction_id if payment else None,
                "paid_on": _paid_on(payment),
                "recorded_by_owner": _recorded_by_owner(payment),
            }
        )

    still_due = [
        {
            "due_id": d.pk,
            "member_id": d.member_id,
            "name": d.member.user.name,
            "first_name": _first_name(d.member.user),
            "email": d.member.user.email,
            "avatar_id": d.member.user.avatar_id,
            "amount": str(quantize_money(d.amount_bdt)),
            "leave_requested": d.member.status == MemberStatus.LEAVE_REQUESTED,
        }
        for d in member_dues
        if d.status == DueStatus.DUE
    ]

    paid_amt = sum((d.amount_bdt for d in dues if d.status == DueStatus.PAID), Decimal("0"))
    expected = charge.amount_bdt

    return {
        "plan": {
            "id": sub.pk,
            "plan_name": sub.plan_name,
            "mode": sub.plan_mode,
            "service_name": {"id": sub.service_name_id, "name": sub.service_name.name},
            "next_renewal": plan_selectors.display_next_renewal(sub),
        },
        "cycle_month": _month_label(charge),
        "charge_due_date": charge.due_date.isoformat(),
        "charge_amount": str(quantize_money(charge.amount_bdt)),
        "waiting": {"count": len(pending), "total": str(quantize_money(waiting_total))},
        "confirmed": {
            "amount": str(quantize_money(paid_amt)),
            "expected": str(quantize_money(expected)),
            "members": len(member_dues),
        },
        "still_due": still_due,
        "pending": pending,
        "decided": decided,
    }


def _empty_review(sub: Subscription) -> dict:
    return {
        "plan": {
            "id": sub.pk,
            "plan_name": sub.plan_name,
            "mode": sub.plan_mode,
            "service_name": {"id": sub.service_name_id, "name": sub.service_name.name},
            "next_renewal": plan_selectors.display_next_renewal(sub),
        },
        "cycle_month": None,
        "charge_due_date": None,
        "charge_amount": None,
        "waiting": {"count": 0, "total": "0.00"},
        "confirmed": {"amount": "0.00", "expected": "0.00", "members": 0},
        "still_due": [],
        "pending": [],
        "decided": [],
    }
