"""Read-only, user-scoped queries for dues and member money views."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import Coalesce

from billing.models import Charge
from billing.services import CHARGE_LEAD_DAYS
from core.dates import today_dhaka
from core.exceptions import NotFound, ValidationFailed
from core.money import quantize_money
from core.schedule import price_at
from dues.models import Due, DueStatus
from dues.splitting import members_for_charge, split_charge
from payments.models import Payment, PaymentAllocation, ReviewStatus
from plans import selectors as plan_selectors
from plans.models import PlanMode, PriceChange, Subscription
from plans.selectors import price_now_dict
from sharing import selectors as sharing_selectors
from sharing.models import Member, MemberStatus, SharedPlan, SplitType


def current_charge(subscription: Subscription, today: date) -> Charge | None:
    past = (
        Charge.objects.filter(subscription=subscription, due_date__lte=today)
        .order_by("-due_date", "-id")
        .first()
    )
    if past:
        return past
    return (
        Charge.objects.filter(subscription=subscription, due_date__gt=today)
        .order_by("due_date", "id")
        .first()
    )


def _first_name(user) -> str:
    return ((user.name or "").strip().split(" ") or [""])[0] or (user.name or "")


@dataclass
class _Period:
    period_start: date
    amount_bdt: Decimal


def project_share_bdt(shared: SharedPlan, member: Member, on_date: date, prices: list) -> Decimal | None:
    amount = quantize_money(price_at(prices, on_date))
    charge = Charge.objects.filter(subscription=shared.subscription_id, period_start=on_date).first()
    if charge:
        period = charge
        total = charge.amount_bdt
    else:
        period = _Period(period_start=on_date, amount_bdt=amount)
        total = amount
    members = members_for_charge(shared, period)
    if member.pk not in {m.pk for m in members}:
        return None
    result = split_charge(shared, members, total)
    if not result.ok:
        return None
    idx = next(i for i, m in enumerate(members) if m.pk == member.pk)
    return result.amounts[idx]


def owner_dues_qs(user, *, params: dict):
    qs = (
        Due.objects.filter(
            charge__subscription__owner=user,
            charge__subscription__archived_on__isnull=True,
        )
        .select_related(
            "charge",
            "charge__subscription",
            "member",
            "member__user",
            "member__shared_plan__subscription",
        )
        .order_by("-charge__due_date", "-id")
    )
    if plan := params.get("plan"):
        qs = qs.filter(charge__subscription_id=plan)
    if member := params.get("member"):
        qs = qs.filter(member_id=member)
    month: date | None = params.get("month")
    if month:
        qs = qs.filter(charge__due_date__year=month.year, charge__due_date__month=month.month)
    if status := params.get("status"):
        allowed = {c.value for c in DueStatus}
        if status not in allowed:
            raise ValidationFailed("Invalid status.", fields={"status": ["Invalid status."]})
        qs = qs.filter(status=status)
    return qs


def parse_dues_list_params(request) -> dict:
    params: dict = {}
    for key, field in (("plan", "plan"), ("member", "member")):
        raw = request.query_params.get(key)
        if raw not in (None, ""):
            try:
                params[field] = int(raw)
            except ValueError:
                raise ValidationFailed(f"Invalid {key}.", fields={key: [f"Invalid {key}."]})
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


def due_list_row(due: Due) -> dict:
    sub = due.charge.subscription
    return {
        "id": due.pk,
        "charge_id": due.charge_id,
        "plan": {"id": sub.pk, "plan_name": sub.plan_name},
        "member": {
            "id": due.member_id,
            "name": due.member.user.name,
            "first_name": _first_name(due.member.user),
            "avatar_id": due.member.user.avatar_id,
        },
        "month": due.charge.period_start.strftime("%Y-%m"),
        "due_date": due.charge.due_date.isoformat(),
        "amount": str(quantize_money(due.amount_bdt)),
        "status": due.status,
        "waiver_note": due.waiver_note,
        "rejection_reason": due.rejection_reason,
        "is_owner_seat": sharing_selectors.is_owner_seat(due.member),
    }


def _payment_brief(payment: Payment | None) -> dict | None:
    if payment is None:
        return None
    paid_at = payment.paid_on.isoformat() if payment.paid_on else None
  # if confirmed might use reviewed_at
    if paid_at is None and payment.reviewed_at:
        paid_at = payment.reviewed_at.date().isoformat()
    return {
        "id": payment.pk,
        "method": payment.method,
        "paid_at": paid_at,
        "review_status": payment.review_status,
    }


def prefetch_member_payment_ctx(shared: SharedPlan, members: list[Member], today: date) -> dict[int, dict]:
    """Per-member due/payment snapshot for the plan's current charge."""
    sub = shared.subscription
    charge = current_charge(sub, today)
    ctx: dict[int, dict] = {m.pk: {} for m in members}
    if charge is None:
        for mid in ctx:
            ctx[mid] = {
                "due_id": None,
                "due_status": None,
                "due_amount": None,
                "last_payment": None,
                "pending_payment_id": None,
            }
        return ctx

    dues = {
        d.member_id: d
        for d in Due.objects.filter(charge=charge, member_id__in=[m.pk for m in members])
    }
    latest_payments = {}
    for p in (
        Payment.objects.filter(shared_plan=shared, member_id__in=dues.keys())
        .order_by("member_id", "-id")
    ):
        if p.member_id not in latest_payments:
            latest_payments[p.member_id] = p

    pending_for_due = {}
    if dues:
        due_ids = [d.pk for d in dues.values()]
        for alloc in PaymentAllocation.objects.filter(
            due_id__in=due_ids, payment__review_status=ReviewStatus.PENDING
        ).select_related("payment"):
            pending_for_due[alloc.due_id] = alloc.payment_id

    for m in members:
        due = dues.get(m.pk)
        ctx[m.pk] = {
            "due_id": due.pk if due else None,
            "due_status": due.status if due else None,
            "due_amount": str(quantize_money(due.amount_bdt)) if due else None,
            "last_payment": _payment_brief(latest_payments.get(m.pk)),
            "pending_payment_id": pending_for_due.get(due.pk) if due else None,
        }
    return ctx


def member_history_rows(member: Member, *, limit: int = 5) -> list[dict]:
    dues = (
        Due.objects.filter(member=member)
        .select_related("charge")
        .order_by("-charge__due_date", "-id")[:limit]
    )
    from payments.selectors import settling_allocations_for_dues, _paid_on, _recorded_by_owner

    due_ids = [d.pk for d in dues]
    alloc_by_due = settling_allocations_for_dues(due_ids)

    rows = []
    for due in dues:
        alloc = alloc_by_due.get(due.pk)
        payment = alloc.payment if alloc else None
        covered_by = None
        if payment and payment.member_id != member.pk:
            covered_by = _first_name(payment.member.user)
        rows.append(
            {
                "due_id": due.pk,
                "month": due.charge.period_start.strftime("%Y-%m"),
                "amount": str(quantize_money(due.amount_bdt)),
                "status": due.status,
                "method": payment.method if payment else None,
                "paid_on": _paid_on(payment),
                "recorded_by_owner": _recorded_by_owner(payment),
                "covered_by": covered_by,
            }
        )
    return rows


def member_balance(member: Member) -> dict:
    qs = Due.objects.filter(
        member=member,
        status__in=(DueStatus.DUE, DueStatus.PENDING),
    ).select_related("charge").order_by("charge__due_date", "id")
    items = [
        {
            "due_id": d.pk,
            "month": d.charge.period_start.strftime("%Y-%m"),
            "amount": str(quantize_money(d.amount_bdt)),
            "status": d.status,
        }
        for d in qs
    ]
    total = sum((d.amount_bdt for d in qs), Decimal("0"))
    return {
        "member_id": member.pk,
        "total_unpaid": str(quantize_money(total)),
        "items": items,
    }


def active_membership(user, plan_id: int) -> Member:
    member = (
        Member.objects.filter(
            user=user,
            shared_plan__subscription_id=plan_id,
            shared_plan__subscription__archived_on__isnull=True,
            status__in=(MemberStatus.ACTIVE, MemberStatus.LEAVE_REQUESTED),
        )
        .select_related("shared_plan__subscription", "user")
        .first()
    )
    if member is None:
        raise NotFound("Not found.")
    if member.shared_plan.subscription.owner_id == user.pk:
        raise NotFound("Not found.")
    return member


def _member_money_snapshot(member: Member, today: date) -> dict:
    sub = member.shared_plan.subscription
    shared = member.shared_plan
    charge = current_charge(sub, today)
    due = None
    if charge:
        due = Due.objects.filter(charge=charge, member=member).first()
    prices = list(PriceChange.objects.filter(subscription=sub).order_by("effective_from", "id"))
    if due:
        my_share = str(quantize_money(due.amount_bdt))
        my_status = due.status
    elif charge:
        proj = project_share_bdt(shared, member, charge.period_start, prices)
        my_share = str(proj) if proj is not None else None
        my_status = "none"
    else:
        my_share = None
        my_status = "none"

    open_dues = Due.objects.filter(member=member, status=DueStatus.DUE)
    open_count = open_dues.count()
    open_amount = open_dues.aggregate(s=Coalesce(Sum("amount_bdt"), Decimal("0")))["s"]
    pending_dues = Due.objects.filter(member=member, status=DueStatus.PENDING)
    pending_amount = pending_dues.aggregate(s=Coalesce(Sum("amount_bdt"), Decimal("0")))["s"]

    return {
        "my_share": my_share,
        "my_status": my_status,
        "open_dues_count": open_count,
        "open_amount": str(quantize_money(open_amount)),
        "pending_amount": str(quantize_money(pending_amount)),
    }


def _sync_member_dues(member: Member, today: date) -> None:
    """Ensure dues exist when a member joined after the charge was locked (idempotent)."""
    from dues import services as dues_services

    sub = member.shared_plan.subscription
    for charge in Charge.objects.filter(subscription=sub, period_start__gte=member.joined_on):
        if Due.objects.filter(charge=charge, member=member).exists():
            continue
        dues_services.recalculate_dues(charge, today, force=True)


def _member_open_dues_rows(member: Member) -> list[dict]:
    open_dues_qs = (
        Due.objects.filter(member=member, status=DueStatus.DUE)
        .select_related("charge")
        .order_by("charge__due_date", "id")
    )
    return [
        {
            "due_id": d.pk,
            "charge_id": d.charge_id,
            "month": d.charge.period_start.strftime("%Y-%m"),
            "due_date": d.charge.due_date.isoformat(),
            "amount": str(quantize_money(d.amount_bdt)),
            "rejection_reason": d.rejection_reason,
        }
        for d in open_dues_qs
    ]


def _member_roster_rows(member: Member) -> list[dict]:
    shared = member.shared_plan
    others = sharing_selectors.members_queryset(shared).exclude(pk=member.pk).select_related("user")
    rows = [
        {
            "id": m.pk,
            "name": m.user.name,
            "first_name": _first_name(m.user),
            "avatar_id": m.user.avatar_id,
            "is_owner": sharing_selectors.is_owner_seat(m),
            "is_you": False,
        }
        for m in others
    ]
    rows.append(
        {
            "id": member.pk,
            "name": member.user.name,
            "first_name": _first_name(member.user),
            "avatar_id": member.user.avatar_id,
            "is_owner": sharing_selectors.is_owner_seat(member),
            "is_you": True,
        }
    )
    return rows


def me_shared_plan_item(member: Member, today: date) -> dict:
    sub = member.shared_plan.subscription
    shared = member.shared_plan
    _sync_member_dues(member, today)
    owner = sub.owner
    snap = _member_money_snapshot(member, today)
    price = price_now_dict(sub)
    taken = sharing_selectors.member_count_active(shared)
    row = {
        "plan_id": sub.pk,
        "plan_name": sub.plan_name,
        "service_name": {"id": sub.service_name_id, "name": sub.service_name.name},
        "owner": {"name": owner.name, "first_name": _first_name(owner), "avatar_id": owner.avatar_id},
        "status": sub.status,
        "cycle": {"unit": sub.cycle_unit, "count": sub.cycle_count},
        "next_renewal": plan_selectors.display_next_renewal(sub),
        "recommended_method": sub.recommended_method,
        "note": sub.note or "",
        "leave_requested": member.status == MemberStatus.LEAVE_REQUESTED,
        "price_now": {k: price[k] for k in ("amount", "currency", "rate", "amount_bdt")} if price else None,
        "seats": shared.seats,
        "seats_taken": taken,
        "open_dues": _member_open_dues_rows(member),
        "members": _member_roster_rows(member),
        **snap,
    }
    return row


def me_shared_plans_qs(user, *, plan_filter: str, today: date):
    base = (
        Member.objects.filter(
            user=user,
            status__in=(MemberStatus.ACTIVE, MemberStatus.LEAVE_REQUESTED),
            shared_plan__subscription__archived_on__isnull=True,
        )
        .exclude(shared_plan__subscription__owner=user)
        .select_related(
            "shared_plan",
            "shared_plan__subscription",
            "shared_plan__subscription__service_name",
            "shared_plan__subscription__owner",
            "user",
        )
        .order_by("-shared_plan__subscription_id")
    )
    if plan_filter == "all":
        return base
    # Filter by current-charge due status (computed in Python for list) — apply coarse SQL first
    if plan_filter not in {"due", "pending", "paid"}:
        raise ValidationFailed("Invalid filter.", fields={"filter": ["Must be all, due, pending, or paid."]})
    return base


def filter_memberships_by_status(memberships: list[Member], plan_filter: str, today: date) -> list[Member]:
    if plan_filter == "all":
        return memberships
    out = []
    for m in memberships:
        snap = _member_money_snapshot(m, today)
        st = snap["my_status"]
        if plan_filter == "due" and st == DueStatus.DUE:
            out.append(m)
        elif plan_filter == "pending" and st == DueStatus.PENDING:
            out.append(m)
        elif plan_filter == "paid" and st == DueStatus.PAID:
            out.append(m)
    return out


def me_shared_plan_counts(memberships: list[Member], today: date) -> dict:
    counts = {"all": len(memberships), "due": 0, "pending": 0, "paid": 0}
    for m in memberships:
        st = _member_money_snapshot(m, today)["my_status"]
        if st in counts:
            counts[st] += 1
    return counts


def me_shared_plan_totals(memberships: list[Member], today: date) -> dict:
    shares = Decimal("0")
    due_now = Decimal("0")
    waiting = Decimal("0")
    due_names: list[str] = []
    waiting_names: list[str] = []
    due_count = 0
    pending_count = 0
    paid_up_count = 0
    for m in memberships:
        snap = _member_money_snapshot(m, today)
        sub = m.shared_plan.subscription
        price = price_now_dict(sub)
        if price:
            shares += Decimal(price["monthly_cost_bdt"])
        due_now += Decimal(snap["open_amount"])
        waiting += Decimal(snap["pending_amount"])
        open_amt = Decimal(snap["open_amount"])
        pend_amt = Decimal(snap["pending_amount"])
        if open_amt > 0:
            due_names.append(sub.plan_name)
            due_count += 1
        if pend_amt > 0:
            waiting_names.append(sub.plan_name)
            pending_count += 1
        if open_amt == 0 and pend_amt == 0:
            paid_up_count += 1
    return {
        "shares": str(quantize_money(shares)),
        "plan_count": len(memberships),
        "due_now": str(quantize_money(due_now)),
        "waiting": str(quantize_money(waiting)),
        "due_names": due_names,
        "waiting_names": waiting_names,
        "due_count": due_count,
        "pending_count": pending_count,
        "paid_up_count": paid_up_count,
    }


def me_shared_plan_detail(member: Member, today: date) -> dict:
    row = me_shared_plan_item(member, today)
    sub = member.shared_plan.subscription
    shared = member.shared_plan
    is_owner_seat = sharing_selectors.is_owner_seat(member)
    row["me"] = {
        "member_id": member.pk,
        "status": member.status,
        "joined_on": member.joined_on.isoformat(),
        "leave_requested_at": (
            member.leave_requested_at.isoformat() if member.leave_requested_at else None
        ),
    }
    row["leave_requested_at"] = row["me"]["leave_requested_at"]
    row["can_request_leave"] = member.status == MemberStatus.ACTIVE and not is_owner_seat
    row["recommended_method"] = sub.recommended_method
    row["mode"] = sub.plan_mode

    row["open_dues"] = _member_open_dues_rows(member)

    pending_pay = (
        Payment.objects.filter(
            shared_plan=shared,
            member=member,
            review_status=ReviewStatus.PENDING,
        )
        .order_by("id")
        .first()
    )
    row["pending_since"] = (
        pending_pay.submitted_at.isoformat() if pending_pay and pending_pay.submitted_at else None
    )

    last_rej = (
        Due.objects.filter(member=member)
        .exclude(rejection_reason="")
        .order_by("-charge__due_date", "-id")
        .values_list("rejection_reason", flat=True)
        .first()
    )
    row["last_rejection"] = last_rej or None

    paid_sum = Due.objects.filter(member=member, status=DueStatus.PAID).aggregate(
        s=Coalesce(Sum("amount_bdt"), Decimal("0"))
    )["s"]
    row["total_spent"] = str(quantize_money(paid_sum))

    history = Due.objects.filter(
        member=member,
        status__in=(DueStatus.PAID, DueStatus.WAIVED),
    ).select_related("charge").order_by("-charge__due_date", "-id")
    row["history"] = [
        {
            "due_id": d.pk,
            "month": d.charge.period_start.strftime("%Y-%m"),
            "amount": str(quantize_money(d.amount_bdt)),
            "status": d.status,
        }
        for d in history
    ]

    row["members"] = _member_roster_rows(member)

    from sharing.selectors import incoming_transfer_for_member
    from sharing.serializers import incoming_transfer_row

    incoming = incoming_transfer_for_member(member.user, sub.pk)
    row["incoming_transfer"] = incoming_transfer_row(incoming) if incoming else None

    coverable = []
    if sub.plan_mode == PlanMode.OWNER:
        cutoff = today + timedelta(days=CHARGE_LEAD_DAYS)
        cover_qs = (
            Due.objects.filter(
                charge__subscription=sub,
                status=DueStatus.DUE,
                charge__due_date__lte=cutoff,
            )
            .exclude(member=member)
            .select_related("member__user", "charge")
            .order_by("charge__due_date", "member_id")
        )
        for d in cover_qs:
            coverable.append(
                {
                    "due_id": d.pk,
                    "name": d.member.user.name,
                    "first_name": _first_name(d.member.user),
                    "month": d.charge.period_start.strftime("%Y-%m"),
                    "amount": str(quantize_money(d.amount_bdt)),
                }
            )
    row["coverable"] = coverable
    from payments.selectors import plan_ious_member

    row["ious"] = plan_ious_member(shared, member)
    return row


def calendar_member_amount(
    member: Member,
    on_date: date,
    prices: list,
    dues_by_period: dict[date, Due],
) -> tuple[str | None, str | None]:
    """Return (amount, status) for calendar member events."""
    shared = member.shared_plan
    row = dues_by_period.get(on_date)
    if row:
        return str(quantize_money(row.amount_bdt)), row.status
    proj = project_share_bdt(shared, member, on_date, prices)
    if proj is None:
        if shared.split_type == SplitType.CUSTOM:
            return None, "due"
        return None, "due"
    return str(proj), "due"
