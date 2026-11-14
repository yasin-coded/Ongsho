"""Owner subscription list/detail enrichment (members, collection, charges)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Count

from billing.models import Charge
from core.money import quantize_money
from dues.models import Due, DueStatus
from payments.models import Payment, PaymentAllocation, ReviewStatus
from plans.models import PlanMode, Subscription, SubscriptionStatus
from plans.selectors import price_now_dict
from sharing import selectors as sharing_selectors
from sharing.models import Member, MemberStatus, SharedPlan


def _first_name(user) -> str:
    return ((user.name or "").strip().split(" ") or [""])[0] or (user.name or "")


def _is_shared(sub: Subscription, shared: SharedPlan | None, seats_taken: int) -> bool:
    if shared is None:
        return False
    if sub.plan_mode == PlanMode.RESELLER:
        return seats_taken > 0
    return seats_taken > 1


def _per_seat_bdt(sub: Subscription, shared: SharedPlan | None, *, is_shared: bool) -> str | None:
    if not is_shared or shared is None or not shared.seats:
        return None
    price = price_now_dict(sub)
    if price is None or not price.get("amount_bdt"):
        return None
    amount = Decimal(price["amount_bdt"])
    return str(quantize_money(amount / Decimal(shared.seats)))


def _member_dues_on_charge(
    charge: Charge | None,
    *,
    sub: Subscription,
    members_by_plan: dict[int, list[Member]],
    dues_by_charge: dict[int, list[Due]],
) -> list[Due]:
    if charge is None:
        return []
    dues = dues_by_charge.get(charge.pk, [])
    if sub.plan_mode == PlanMode.RESELLER:
        return [d for d in dues if d.member.user_id != sub.owner_id]
    owner_id = sub.owner_id
    return [d for d in dues if d.member.user_id != owner_id]


def _collected_expected(member_dues: list[Due]) -> tuple[str | None, str | None]:
    active = [d for d in member_dues if d.status != DueStatus.WAIVED]
    if not active:
        return "0.00", "0.00"
    collected = sum((d.amount_bdt for d in active if d.status == DueStatus.PAID), Decimal("0"))
    expected = sum((d.amount_bdt for d in active), Decimal("0"))
    return str(quantize_money(collected)), str(quantize_money(expected))


def _cycle_dues_for_progress(
    charge: Charge | None,
    *,
    sub: Subscription,
    dues_by_charge: dict[int, list[Due]],
) -> list[Due]:
    """Dues counted toward the owner plan progress bar (full cycle, incl. owner seat)."""
    if charge is None:
        return []
    dues = dues_by_charge.get(charge.pk, [])
    if sub.plan_mode == PlanMode.RESELLER:
        return [d for d in dues if d.member.user_id != sub.owner_id]
    return dues


def _confirmed_so_far_amounts(charge: Charge, cycle_dues: list[Due]) -> dict[str, str]:
    paid = sum((d.amount_bdt for d in cycle_dues if d.status == DueStatus.PAID), Decimal("0"))
    waived = sum((d.amount_bdt for d in cycle_dues if d.status == DueStatus.WAIVED), Decimal("0"))
    pending = sum((d.amount_bdt for d in cycle_dues if d.status == DueStatus.PENDING), Decimal("0"))
    return {
        "paid": str(quantize_money(paid)),
        "waived": str(quantize_money(waived)),
        "pending": str(quantize_money(pending)),
        "expected": str(quantize_money(charge.amount_bdt)),
    }


class OwnerPlanContext:
    def __init__(self, today: date):
        self.today = today
        self.shared_by_sub: dict[int, SharedPlan] = {}
        self.members_by_sub: dict[int, list[Member]] = {}
        self.charges_by_sub: dict[int, list[Charge]] = {}
        self.current_charge_by_sub: dict[int, Charge | None] = {}
        self.dues_by_charge: dict[int, list[Due]] = {}
        self.pending_by_sub: dict[int, int] = {}

    def seats_taken(self, sub_id: int) -> int:
        return len(self.members_by_sub.get(sub_id, []))

    def shared(self, sub_id: int) -> SharedPlan | None:
        return self.shared_by_sub.get(sub_id)


def prefetch_owner_plan_context(subscriptions: list[Subscription], today: date) -> OwnerPlanContext:
    ctx = OwnerPlanContext(today)
    if not subscriptions:
        return ctx
    sub_ids = [s.pk for s in subscriptions]
    ctx.shared_by_sub = {
        sp.subscription_id: sp
        for sp in SharedPlan.objects.filter(subscription_id__in=sub_ids).select_related("subscription")
    }
    members = list(
        Member.objects.filter(shared_plan__subscription_id__in=sub_ids)
        .exclude(status=MemberStatus.LEFT)
        .select_related("user", "shared_plan")
        .order_by("joined_on", "id")
    )
    for m in members:
        sid = m.shared_plan.subscription_id
        ctx.members_by_sub.setdefault(sid, []).append(m)

    charges = list(Charge.objects.filter(subscription_id__in=sub_ids).order_by("-due_date", "-id"))
    for ch in charges:
        ctx.charges_by_sub.setdefault(ch.subscription_id, []).append(ch)

    for sub in subscriptions:
        chs = ctx.charges_by_sub.get(sub.pk, [])
        past = [c for c in chs if c.due_date <= today]
        if past:
            ctx.current_charge_by_sub[sub.pk] = max(past, key=lambda c: (c.due_date, c.pk))
        else:
            future = [c for c in chs if c.due_date > today]
            ctx.current_charge_by_sub[sub.pk] = (
                min(future, key=lambda c: (c.due_date, c.pk)) if future else None
            )

    charge_ids = [c.pk for c in ctx.current_charge_by_sub.values() if c]
    if charge_ids:
        for due in Due.objects.filter(charge_id__in=charge_ids).select_related("member__user", "member"):
            ctx.dues_by_charge.setdefault(due.charge_id, []).append(due)

    for row in (
        Payment.objects.filter(
            shared_plan__subscription_id__in=sub_ids,
            review_status=ReviewStatus.PENDING,
        )
        .values("shared_plan__subscription_id")
        .annotate(c=Count("id"))
    ):
        ctx.pending_by_sub[row["shared_plan__subscription_id"]] = row["c"]

    return ctx


def owner_list_extra(sub: Subscription, ctx: OwnerPlanContext) -> dict:
    shared = ctx.shared(sub.pk)
    taken = ctx.seats_taken(sub.pk)
    is_shared = _is_shared(sub, shared, taken)
    charge = ctx.current_charge_by_sub.get(sub.pk)
    member_dues = _member_dues_on_charge(
        charge, sub=sub, members_by_plan=ctx.members_by_sub, dues_by_charge=ctx.dues_by_charge
    )

    seats = shared.seats if shared else None
    collected, expected = _collected_expected(member_dues) if is_shared and charge else (None, None)
    if not is_shared or charge is None:
        collected, expected = None, None

    members_out = []
    pending_count = 0
    if charge and is_shared:
        due_by_member = {d.member_id: d for d in ctx.dues_by_charge.get(charge.pk, [])}
        for m in ctx.members_by_sub.get(sub.pk, []):
            if sub.plan_mode == PlanMode.RESELLER and m.user_id == sub.owner_id:
                continue
            due = due_by_member.get(m.pk)
            due_status = due.status if due else None
            if due_status == DueStatus.PENDING:
                pending_count += 1
            members_out.append(
                {
                    "id": m.pk,
                    "name": m.user.name,
                    "first_name": _first_name(m.user),
                    "avatar_id": m.user.avatar_id,
                    "is_owner_seat": sharing_selectors.is_owner_seat(m),
                    "due_status": due_status,
                }
            )

    return {
        "seats": seats,
        "seats_taken": taken if shared else None,
        "per_seat": _per_seat_bdt(sub, shared, is_shared=is_shared),
        "members": members_out,
        "pending_count": pending_count if is_shared and charge else 0,
        "collected": collected,
        "expected": expected,
    }


def subscription_list_totals_from_ctx(
    all_owned: list[Subscription], ctx: OwnerPlanContext, user
) -> dict:
    from plans.selectors import subscription_list_totals

    base = subscription_list_totals(user)

    confirmed = Decimal("0")
    pending = Decimal("0")
    expected = Decimal("0")
    review_count = 0
    review_plans: list[dict] = []

    for sub in all_owned:
        if sub.status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL):
            continue
        shared = ctx.shared(sub.pk)
        taken = ctx.seats_taken(sub.pk)
        if _is_shared(sub, shared, taken):
            charge = ctx.current_charge_by_sub.get(sub.pk)
            if charge:
                member_dues = _member_dues_on_charge(
                    charge, sub=sub, members_by_plan=ctx.members_by_sub, dues_by_charge=ctx.dues_by_charge
                )
                active = [d for d in member_dues if d.status != DueStatus.WAIVED]
                confirmed += sum((d.amount_bdt for d in active if d.status == DueStatus.PAID), Decimal("0"))
                pending += sum((d.amount_bdt for d in active if d.status == DueStatus.PENDING), Decimal("0"))
                expected += sum((d.amount_bdt for d in active), Decimal("0"))

        cnt = ctx.pending_by_sub.get(sub.pk, 0)
        if cnt:
            review_count += cnt
            review_plans.append({"id": sub.pk, "plan_name": sub.plan_name, "count": cnt})

    base["confirmed"] = str(quantize_money(confirmed))
    base["pending"] = str(quantize_money(pending))
    base["expected"] = str(quantize_money(expected))
    base["review_count"] = review_count
    base["review_plans"] = sorted(review_plans, key=lambda x: x["plan_name"].lower())
    return base


def _charge_has_payments(charge_id: int, dues: list[Due], owner_id: int) -> bool:
    due_ids = [d.pk for d in dues]
    if not due_ids:
        return False
    for alloc in PaymentAllocation.objects.filter(
        due_id__in=due_ids,
        payment__review_status=ReviewStatus.CONFIRMED,
    ).select_related("payment__member"):
        if alloc.payment.member.user_id != owner_id:
            return True
    return False


def _due_status_counts(dues: list[Due]) -> dict[str, int]:
    counts = {DueStatus.DUE: 0, DueStatus.PENDING: 0, DueStatus.PAID: 0, DueStatus.WAIVED: 0}
    for d in dues:
        counts[d.status] = counts.get(d.status, 0) + 1
    return {
        "due": counts[DueStatus.DUE],
        "pending": counts[DueStatus.PENDING],
        "paid": counts[DueStatus.PAID],
        "waived": counts[DueStatus.WAIVED],
    }


def owner_detail_extra(sub: Subscription, today: date) -> dict:
    ctx = prefetch_owner_plan_context([sub], today)
    shared = ctx.shared(sub.pk)
    leave_requests = [
        {
            "member_id": m.pk,
            "name": m.user.name,
            "first_name": _first_name(m.user),
            "leave_requested_at": m.leave_requested_at.isoformat() if m.leave_requested_at else None,
        }
        for m in ctx.members_by_sub.get(sub.pk, [])
        if m.status == MemberStatus.LEAVE_REQUESTED
    ]

    charge_ids = [c.pk for c in ctx.charges_by_sub.get(sub.pk, [])]
    if charge_ids:
        all_dues = list(
            Due.objects.filter(charge_id__in=charge_ids).select_related("member")
        )
        dues_by_charge: dict[int, list[Due]] = defaultdict(list)
        for d in all_dues:
            dues_by_charge[d.charge_id].append(d)
    else:
        dues_by_charge = {}

    charges_out = []
    for ch in ctx.charges_by_sub.get(sub.pk, []):
        dues = dues_by_charge.get(ch.pk, [])
        charges_out.append(
            {
                "id": ch.pk,
                "month": ch.period_start.strftime("%Y-%m"),
                "due_date": ch.due_date.isoformat(),
                "amount": str(quantize_money(ch.amount)),
                "amount_bdt": str(quantize_money(ch.amount_bdt)),
                "status": ch.status,
                "locked": ch.locked,
                "has_payments": _charge_has_payments(ch.pk, dues, sub.owner_id),
                "dues": _due_status_counts(dues),
            }
        )

    taken = ctx.seats_taken(sub.pk)
    is_shared = _is_shared(sub, shared, taken)
    charge = ctx.current_charge_by_sub.get(sub.pk)
    member_dues = (
        _member_dues_on_charge(
            charge,
            sub=sub,
            members_by_plan=ctx.members_by_sub,
            dues_by_charge=dues_by_charge,
        )
        if charge
        else []
    )
    collected, expected = (
        _collected_expected(member_dues) if is_shared and charge and member_dues else (None, None)
    )
    cycle_dues = (
        _cycle_dues_for_progress(charge, sub=sub, dues_by_charge=dues_by_charge)
        if charge
        else []
    )
    confirmed_so_far = (
        _confirmed_so_far_amounts(charge, cycle_dues) if is_shared and charge else None
    )

    owner_member = None
    if shared:
        for m in ctx.members_by_sub.get(sub.pk, []):
            if sharing_selectors.is_owner_seat(m):
                owner_member = m
                break
    from dues import selectors as dues_selectors

    coverable_dues = (
        dues_selectors.coverable_dues_for_viewer(owner_member, today) if owner_member else []
    )

    return {
        "split_type": shared.split_type if shared else None,
        "charges": charges_out,
        "leave_requests": leave_requests,
        "collected": collected,
        "expected": expected,
        "confirmed_so_far": confirmed_so_far,
        "coverable_dues": coverable_dues,
    }
