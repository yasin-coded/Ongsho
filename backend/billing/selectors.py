from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Exists, OuterRef, Q

from billing.models import Charge
from core.exceptions import NotFound
from core.money import quantize_money, to_bdt
from core.schedule import Schedule, due_dates_between, first_bill_date, price_at, stop_date
from plans.models import PriceChange, Subscription, SubscriptionStatus
from sharing.models import Member, MemberStatus


def schedule_for_subscription(sub) -> Schedule:
    return Schedule(
        start_date=sub.start_date,
        trial_end_date=sub.trial_end_date,
        anchor_day=sub.anchor_day,
        cycle_unit=sub.cycle_unit,
        cycle_count=sub.cycle_count,
        renewal_type=sub.renewal_type,
        end_date=sub.end_date,
        paused_on=sub.paused_on,
        cancelled_on=sub.cancelled_on,
        status=sub.status,
        billing_from=sub.billing_from,
    )


def owned_charge(user, charge_id: int) -> Charge:
    row = (
        Charge.objects.filter(pk=charge_id, subscription__owner=user, subscription__archived_on__isnull=True)
        .select_related("subscription")
        .first()
    )
    if row is None:
        raise NotFound("Charge not found.")
    return row


def owner_charges_qs(user, *, params: dict):
    from payments.models import PaymentAllocation
    from sharing.models import Member

    non_owner_payment = PaymentAllocation.objects.filter(
        due__charge_id=OuterRef("pk"),
        payment__member__shared_plan__subscription_id=OuterRef("subscription_id"),
    ).exclude(payment__member__user=user)
    qs = (
        Charge.objects.filter(subscription__owner=user, subscription__archived_on__isnull=True)
        .select_related("subscription")
        .annotate(_has_payments=Exists(non_owner_payment))
        .order_by("-due_date", "-id")
    )
    if plan := params.get("plan"):
        qs = qs.filter(subscription_id=plan)
    if status := params.get("status"):
        qs = qs.filter(status=status)
    month = params.get("month")
    if month:
        qs = qs.filter(due_date__year=month.year, due_date__month=month.month)
    return qs


def _month_last_day(month_start: date) -> date:
    last = monthrange(month_start.year, month_start.month)[1]
    return date(month_start.year, month_start.month, last)


def _rate_on_or_before(user_id: int, on_date: date):
    from plans.models import ExchangeRate

    return (
        ExchangeRate.objects.filter(user_id=user_id, rate_date__lte=on_date)
        .order_by("-rate_date", "-id")
        .first()
    )


def _bdt_at(sub: Subscription, on_date: date, prices: list) -> str | None:
    amount = quantize_money(price_at(prices, on_date))
    if sub.currency == "BDT":
        return str(amount)
    rate = _rate_on_or_before(sub.owner_id, on_date)
    if rate is None:
        return None
    return str(to_bdt(amount, rate.usd_to_bdt))


def _owner_schedule_events(
    sub: Subscription,
    today: date,
    range_start: date,
    range_end: date,
    prices: list,
) -> list[dict]:
    schedule = schedule_for_subscription(sub)
    first = first_bill_date(sub.start_date, sub.trial_end_date)
    scan_from = min(range_start, first)
    raw_dates = due_dates_between(schedule, scan_from, range_end)
    out: list[dict] = []
    for due in raw_dates:
        if due < range_start or due > range_end:
            continue
        if due >= today and due < sub.billing_from:
            continue
        amount = _bdt_at(sub, due, prices)
        kind = "trial_end" if sub.trial_end_date and due == sub.trial_end_date else "renews"
        out.append(
            {
                "id": f"o-{sub.pk}-{due.isoformat()}",
                "date": due.isoformat(),
                "plan_id": sub.pk,
                "plan_name": sub.plan_name,
                "role": "owner",
                "kind": kind,
                "amount": amount,
                "status": None,
            }
        )
    if sub.renewal_type == "fixed_term" and sub.end_date:
        end = sub.end_date
        if range_start <= end <= range_end:
            out.append(
                {
                    "id": f"o-{sub.pk}-exp-{end.isoformat()}",
                    "date": end.isoformat(),
                    "plan_id": sub.pk,
                    "plan_name": sub.plan_name,
                    "role": "owner",
                    "kind": "expires",
                    "amount": "0",
                    "status": None,
                }
            )
    return out


def _member_schedule_events(
    member: Member,
    today: date,
    range_start: date,
    range_end: date,
) -> list[dict]:
    from dues.models import Due

    sub = member.shared_plan.subscription
    if sub.archived_on is not None or sub.owner_id == member.user_id:
        return []
    schedule = schedule_for_subscription(sub)
    from_date = max(member.joined_on, range_start)
    to_date = range_end
    if member.left_on:
        to_date = min(to_date, member.left_on)
    prices = list(PriceChange.objects.filter(subscription=sub).order_by("effective_from", "id"))
    dates = due_dates_between(schedule, member.joined_on, to_date)
    dues_by_charge_date = {}
    for due in Due.objects.filter(member=member).select_related("charge"):
        dues_by_charge_date[due.charge.due_date] = due
    out: list[dict] = []
    for due in dates:
        if due < from_date or due > to_date:
            continue
        if due < range_start or due > range_end:
            continue
        row = dues_by_charge_date.get(due)
        out.append(
            {
                "id": f"m-{member.pk}-{due.isoformat()}",
                "date": due.isoformat(),
                "plan_id": sub.pk,
                "plan_name": sub.plan_name,
                "role": "member",
                "kind": "due",
                "amount": str(row.amount_bdt) if row else None,
                "status": row.status if row else "due",
            }
        )
    return out


def calendar_events(user, *, today: date, month_start: date) -> list[dict]:
    range_start = month_start
    month_end = _month_last_day(month_start)
    range_end = max(month_end, today + timedelta(days=6))
    events: list[dict] = []
    owned = Subscription.objects.filter(owner=user, archived_on__isnull=True).order_by("plan_name")
    for sub in owned:
        prices = list(PriceChange.objects.filter(subscription=sub).order_by("effective_from", "id"))
        if not prices:
            continue
        events.extend(_owner_schedule_events(sub, today, range_start, range_end, prices))
    memberships = (
        Member.objects.filter(
            user=user,
            status__in=(MemberStatus.ACTIVE, MemberStatus.LEAVE_REQUESTED),
        )
        .select_related("shared_plan__subscription")
        .exclude(shared_plan__subscription__owner=user)
        .filter(shared_plan__subscription__archived_on__isnull=True)
    )
    for member in memberships:
        events.extend(_member_schedule_events(member, today, range_start, range_end))
    events.sort(key=lambda e: (e["date"], e["plan_name"]))
    return events
