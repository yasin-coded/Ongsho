"""Read-only, user-scoped dashboard and forecast selectors."""

from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Q
from django.utils import timezone

from billing.models import Charge
from billing.selectors import _bdt_at, _month_last_day, calendar_events, schedule_for_subscription
from core.exceptions import ValidationFailed
from core.money import quantize_money
from core.schedule import monthly_equivalent
from core.schedule import due_dates_between, stop_date
from dues.models import Due, DueStatus
from dues.selectors import project_share_bdt
from payments.models import Payment, ReviewStatus
from plans.models import CycleUnit, PlanMode, PriceChange, RenewalType, Subscription, SubscriptionStatus
from plans.owner_selectors import _is_shared
from sharing.models import Invite, InviteStatus, Member, MemberStatus, OwnershipTransfer, SharedPlan, TransferStatus

_ACTIVE = {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}


def _first_name(user) -> str:
    return ((user.name or "").strip().split(" ") or [""])[0] or (user.name or "")


def parse_month_param(request, today: date) -> date:
    raw = request.query_params.get("month")
    if raw in (None, ""):
        return date(today.year, today.month, 1)
    try:
        parts = raw.split("-")
        year, month = int(parts[0]), int(parts[1])
        if not (1 <= month <= 12):
            raise ValueError
        return date(year, month, 1)
    except (ValueError, IndexError):
        raise ValidationFailed("Invalid month.", fields={"month": ["Use YYYY-MM."]})


def parse_forecast_months(request) -> int:
    raw = request.query_params.get("months", "12")
    try:
        n = int(raw)
    except ValueError:
        raise ValidationFailed("Invalid months.", fields={"months": ["Enter a number from 1 to 12."]})
    if not 1 <= n <= 12:
        raise ValidationFailed("Invalid months.", fields={"months": ["Enter a number from 1 to 12."]})
    return n


def _eligible_owned(user):
    return Subscription.objects.filter(
        owner=user,
        archived_on__isnull=True,
        status__in=_ACTIVE,
    ).select_related("service_name", "category", "owner")


def _eligible_memberships(user):
    return (
        Member.objects.filter(
            user=user,
            status__in=(MemberStatus.ACTIVE, MemberStatus.LEAVE_REQUESTED),
        )
        .exclude(shared_plan__subscription__owner=user)
        .filter(shared_plan__subscription__archived_on__isnull=True)
        .filter(shared_plan__subscription__status__in=_ACTIVE)
        .select_related("shared_plan__subscription", "shared_plan__subscription__category", "user")
    )


class DashCtx:
    def __init__(self, user, today: date):
        self.user = user
        self.today = today
        self.subs_owned = list(_eligible_owned(user))
        self.memberships = list(_eligible_memberships(user))
        sub_ids = {s.pk for s in self.subs_owned} | {m.shared_plan.subscription_id for m in self.memberships}
        self.shared_by_sub = {
            sp.subscription_id: sp
            for sp in SharedPlan.objects.filter(subscription_id__in=sub_ids)
        }
        self.members_by_sub: dict[int, list[Member]] = defaultdict(list)
        if sub_ids:
            for m in Member.objects.filter(shared_plan__subscription_id__in=sub_ids).exclude(
                status=MemberStatus.LEFT
            ).select_related("user", "shared_plan"):
                self.members_by_sub[m.shared_plan.subscription_id].append(m)
        self.charges_by_sub: dict[int, list[Charge]] = defaultdict(list)
        if sub_ids:
            for ch in Charge.objects.filter(subscription_id__in=sub_ids):
                self.charges_by_sub[ch.subscription_id].append(ch)
        self.prices_by_sub: dict[int, list] = defaultdict(list)
        if sub_ids:
            for pc in PriceChange.objects.filter(subscription_id__in=sub_ids).order_by("effective_from", "id"):
                self.prices_by_sub[pc.subscription_id].append(pc)
        self.dues_by_charge: dict[int, list[Due]] = defaultdict(list)
        charge_ids = [c.pk for chs in self.charges_by_sub.values() for c in chs]
        if charge_ids:
            for d in Due.objects.filter(charge_id__in=charge_ids).select_related("member", "charge"):
                self.dues_by_charge[d.charge_id].append(d)
        self.dues_by_member_plan: dict[tuple[int, int], list[Due]] = defaultdict(list)
        for d in self.dues_by_charge.values():
            for due in d:
                sid = due.charge.subscription_id
                self.dues_by_member_plan[(sid, due.member_id)].append(due)

    def charge_on_date(self, sub_id: int, on_date: date) -> Charge | None:
        for ch in self.charges_by_sub.get(sub_id, []):
            if ch.due_date == on_date or ch.period_start == on_date:
                return ch
        return None

    def member_row(self, sub_id: int, user_id: int) -> Member | None:
        for m in self.members_by_sub.get(sub_id, []):
            if m.user_id == user_id:
                return m
        return None


def _schedule_dates_in_range(sub: Subscription, start: date, end: date, today: date) -> list[date]:
    sched = schedule_for_subscription(sub)
    stop = stop_date(sched)
    raw_end = min(end, stop) if stop else end
    dates = due_dates_between(sched, sub.start_date, raw_end)
    out = []
    for d in dates:
        if d < start or d > end:
            continue
        if d < sub.billing_from:
            continue
        out.append(d)
    return out


def my_portion(
    ctx: DashCtx,
    *,
    sub: Subscription,
    role: str,
    on_date: date,
    member: Member | None,
) -> Decimal:
    if sub.plan_mode == PlanMode.RESELLER and role == "owner":
        return Decimal("0")
    shared = ctx.shared_by_sub.get(sub.pk)
    taken = len(ctx.members_by_sub.get(sub.pk, []))
    is_shared = _is_shared(sub, shared, taken)
    prices = ctx.prices_by_sub.get(sub.pk, [])

    if role == "owner" and not is_shared:
        raw = _bdt_at(sub, on_date, prices)
        return Decimal(raw) if raw else Decimal("0")

    if role == "owner" and is_shared:
        owner_seat = None
        for m in ctx.members_by_sub.get(sub.pk, []):
            if m.user_id == sub.owner_id:
                owner_seat = m
                break
        if owner_seat is None:
            return Decimal("0")
        ch = ctx.charge_on_date(sub.pk, on_date)
        if ch:
            for due in ctx.dues_by_charge.get(ch.pk, []):
                if due.member_id == owner_seat.pk:
                    return quantize_money(due.amount_bdt)
        proj = project_share_bdt(shared, owner_seat, on_date, prices) if shared else None
        return quantize_money(proj) if proj is not None else Decimal("0")

    if member is None:
        member = ctx.member_row(sub.pk, sub.owner_id)
    if member is None:
        return Decimal("0")

    ch = ctx.charge_on_date(sub.pk, on_date)
    if ch:
        for due in ctx.dues_by_charge.get(ch.pk, []):
            if due.member_id == member.pk:
                return quantize_money(due.amount_bdt)
    proj = project_share_bdt(shared, member, on_date, prices) if shared else None
    return quantize_money(proj) if proj is not None else Decimal("0")


def _spend_rows(ctx: DashCtx, month_start: date) -> list[dict]:
    month_end = _month_last_day(month_start)
    rows = []
    for sub in ctx.subs_owned:
        for d in _schedule_dates_in_range(sub, month_start, month_end, ctx.today):
            amt = my_portion(ctx, sub=sub, role="owner", on_date=d, member=None)
            if amt > 0:
                rows.append(
                    {
                        "plan_id": sub.pk,
                        "plan_name": sub.plan_name,
                        "role": "owner",
                        "date": d.isoformat(),
                        "amount": str(amt),
                        "yearly": sub.cycle_unit == CycleUnit.YEAR,
                        "category": {"id": sub.category_id, "name": sub.category.name},
                    }
                )
    for mem in ctx.memberships:
        sub = mem.shared_plan.subscription
        for d in _schedule_dates_in_range(sub, month_start, month_end, ctx.today):
            if d < mem.joined_on:
                continue
            if mem.left_on and d > mem.left_on:
                continue
            amt = my_portion(ctx, sub=sub, role="member", on_date=d, member=mem)
            if amt > 0:
                rows.append(
                    {
                        "plan_id": sub.pk,
                        "plan_name": sub.plan_name,
                        "role": "member",
                        "date": d.isoformat(),
                        "amount": str(amt),
                        "yearly": sub.cycle_unit == CycleUnit.YEAR,
                        "category": {"id": sub.category_id, "name": sub.category.name},
                    }
                )
    return rows


def _due_soon(ctx: DashCtx) -> dict:
    end = ctx.today + timedelta(days=6)
    events = calendar_events(ctx.user, today=ctx.today, month_start=ctx.today)
    items = []
    for e in events:
        d = date.fromisoformat(e["date"])
        if d < ctx.today or d > end:
            continue
        if e["role"] == "owner" and e["kind"] in ("renews", "trial_end"):
            items.append(
                {
                    "plan_id": e["plan_id"],
                    "plan_name": e["plan_name"],
                    "date": e["date"],
                    "kind": "trial_end" if e["kind"] == "trial_end" else "renews",
                    "amount": e["amount"],
                    "role": "owner",
                }
            )
        elif e["role"] == "member" and e.get("status") == DueStatus.DUE and e["kind"] == "due":
            items.append(
                {
                    "plan_id": e["plan_id"],
                    "plan_name": e["plan_name"],
                    "date": e["date"],
                    "kind": "due",
                    "amount": e["amount"],
                    "role": "member",
                }
            )
    items.sort(key=lambda x: (x["date"], x["plan_name"]))
    total = sum((Decimal(i["amount"]) for i in items if i.get("amount")), Decimal("0"))
    return {
        "count": len(items),
        "total": str(quantize_money(total)),
        "first": items[0]["date"] if items else None,
        "items": items,
    }


def _rarely(ctx: DashCtx) -> dict:
    plans = []
    yearly = Decimal("0")
    for sub in ctx.subs_owned:
        if not sub.rarely_used:
            continue
        plans.append(
            {
                "id": sub.pk,
                "plan_name": sub.plan_name,
                "service_name": sub.service_name.name,
            }
        )
        charge = None
        past = [c for c in ctx.charges_by_sub.get(sub.pk, []) if c.due_date <= ctx.today]
        if past:
            charge = max(past, key=lambda c: (c.due_date, c.pk))
        on = charge.period_start if charge else ctx.today
        portion = my_portion(ctx, sub=sub, role="owner", on_date=on, member=None)
        yearly += monthly_equivalent(portion, sub.cycle_unit, sub.cycle_count) * Decimal("12")
    return {"plans": plans, "yearly": str(quantize_money(yearly))}


def _attention(user, today: date) -> list[dict]:
    items = []
    owned = Subscription.objects.filter(owner=user, archived_on__isnull=True)
    pending_by_plan = {
        row["shared_plan__subscription_id"]: row["c"]
        for row in Payment.objects.filter(
            shared_plan__subscription__owner=user,
            review_status=ReviewStatus.PENDING,
        )
        .values("shared_plan__subscription_id")
        .annotate(c=Count("id"))
    }
    for sub in owned:
        cnt = pending_by_plan.get(sub.pk, 0)
        if cnt:
            items.append(
                {
                    "kind": "review",
                    "plan_id": sub.pk,
                    "plan_name": sub.plan_name,
                    "title": f"{cnt} payments to review",
                    "detail": f"{sub.plan_name} · transaction IDs waiting",
                    "count": cnt,
                    "link": f"/app/plans/{sub.pk}/review",
                    "payload": {"plan_id": sub.pk},
                }
            )
    for m in Member.objects.filter(
        shared_plan__subscription__owner=user,
        status=MemberStatus.LEAVE_REQUESTED,
    ).select_related("user", "shared_plan__subscription"):
        sub = m.shared_plan.subscription
        items.append(
            {
                "kind": "leave",
                "plan_id": sub.pk,
                "plan_name": sub.plan_name,
                "title": f"{_first_name(m.user)} wants to leave",
                "detail": f"{sub.plan_name} · needs your OK",
                "count": 1,
                "link": f"/app/plans/{sub.pk}?leave={m.pk}",
                "payload": {"member_id": m.pk, "plan_id": sub.pk},
            }
        )
    if user.email_verified:
        for inv in Invite.objects.filter(
            email=user.email.lower(),
            status=InviteStatus.PENDING,
            expires_on__gt=timezone.now(),
        ).select_related("shared_plan__subscription", "invited_by"):
            sub = inv.shared_plan.subscription
            items.append(
                {
                    "kind": "invite",
                    "plan_id": sub.pk,
                    "plan_name": sub.plan_name,
                    "title": f"Invite from {_first_name(inv.invited_by)}",
                    "detail": sub.plan_name,
                    "count": 1,
                    "link": f"/app/invites",
                    "payload": {"invite_id": inv.pk},
                }
            )
    for tr in OwnershipTransfer.objects.filter(to_user=user, status=TransferStatus.PENDING).select_related(
        "shared_plan__subscription", "from_user"
    ):
        sub = tr.shared_plan.subscription
        items.append(
            {
                "kind": "transfer",
                "plan_id": sub.pk,
                "plan_name": sub.plan_name,
                "title": f"Transfer from {_first_name(tr.from_user)}",
                "detail": sub.plan_name,
                "count": 1,
                "link": f"/app/plans/{sub.pk}",
                "payload": {"transfer_id": tr.pk},
            }
        )
    return items


def _by_category(rows: list[dict]) -> list[dict]:
    totals: dict[int, dict] = {}
    for r in rows:
        cat = r["category"]
        cid = cat["id"]
        if cid not in totals:
            totals[cid] = {"category_id": cid, "name": cat["name"], "amount": Decimal("0")}
        totals[cid]["amount"] += Decimal(r["amount"])
    out = [
        {**v, "amount": str(quantize_money(v["amount"]))}
        for v in totals.values()
    ]
    out.sort(key=lambda x: Decimal(x["amount"]), reverse=True)
    return out


def _next7(ctx: DashCtx) -> list[dict]:
    end = ctx.today + timedelta(days=6)
    events = calendar_events(ctx.user, today=ctx.today, month_start=ctx.today)
    return [e for e in events if ctx.today <= date.fromisoformat(e["date"]) <= end]


def dashboard_summary(user, *, month: date, today: date) -> dict:
    ctx = DashCtx(user, today)
    rows = _spend_rows(ctx, month)
    owned = sum((Decimal(r["amount"]) for r in rows if r["role"] == "owner"), Decimal("0"))
    joined = sum((Decimal(r["amount"]) for r in rows if r["role"] == "member"), Decimal("0"))
    month_key = month.strftime("%Y-%m")
    return {
        "first_name": _first_name(user),
        "month": month_key,
        "spend": {
            "total": str(quantize_money(owned + joined)),
            "owned": str(quantize_money(owned)),
            "joined": str(quantize_money(joined)),
            "rows": rows,
        },
        "due_soon": _due_soon(ctx),
        "rarely": _rarely(ctx),
        "attention": _attention(user, today),
        "next7": _next7(ctx),
        "by_category": _by_category(rows),
        "counts": {
            "owned_plans": len(ctx.subs_owned),
            "joined_plans": len(ctx.memberships),
        },
    }


def _month_add(key: str, n: int) -> str:
    y, m = int(key[:4]), int(key[5:7])
    m += n
    while m > 12:
        m -= 12
        y += 1
    while m < 1:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}"


def dashboard_forecast(user, *, months: int, today: date) -> list[dict]:
    ctx = DashCtx(user, today)
    start_key = today.strftime("%Y-%m")
    current_key = start_key
    out = []
    for i in range(months):
        key = _month_add(start_key, i)
        y, m = int(key[:4]), int(key[5:7])
        month_start = date(y, m, 1)
        month_end = _month_last_day(month_start)
        rows = _spend_rows(ctx, month_start)
        has_yearly = any(
            sub.cycle_unit == CycleUnit.YEAR
            for sub in ctx.subs_owned
            for _d in _schedule_dates_in_range(sub, month_start, month_end, ctx.today)
        )
        if has_yearly:
            kind = "yearly"
        elif key == current_key:
            kind = "this"
        else:
            kind = "regular"
        label = month_start.strftime("%b")
        total = sum((Decimal(r["amount"]) for r in rows), Decimal("0"))
        out.append(
            {
                "key": key,
                "label": label,
                "year": key[:4],
                "total": str(quantize_money(total)),
                "kind": kind,
                "yearly_plans": list(
                    {
                        sub.plan_name
                        for sub in ctx.subs_owned
                        if sub.cycle_unit == CycleUnit.YEAR
                        for _d in _schedule_dates_in_range(sub, month_start, month_end, ctx.today)
                    }
                ),
            }
        )
    return out
