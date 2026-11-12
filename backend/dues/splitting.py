from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Case, IntegerField, Q, Value, When

from billing.models import Charge
from core.money import quantize_money, split_exact
from plans.models import PlanMode
from sharing.models import Member, SharedPlan, SplitType


@dataclass(frozen=True)
class SplitResult:
    ok: bool
    amounts: list[Decimal]
    reason: str = ""


def members_for_charge(shared: SharedPlan, charge: Charge) -> list[Member]:
    period_start = charge.period_start
    sub = shared.subscription
    qs = Member.objects.filter(
        shared_plan=shared,
        joined_on__lte=period_start,
    ).filter(Q(left_on__isnull=True) | Q(left_on__gt=period_start))
    if sub.plan_mode == PlanMode.OWNER:
        qs = qs.annotate(
            sort_owner=Case(
                When(user_id=sub.owner_id, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by("sort_owner", "joined_on", "id")
    else:
        qs = qs.order_by("joined_on", "id")
    return list(qs)


def split_charge(shared: SharedPlan, members: list[Member], amount_bdt: Decimal) -> SplitResult:
    if not members:
        return SplitResult(ok=False, amounts=[], reason="no_members")
    total = quantize_money(Decimal(amount_bdt))
    if shared.split_type == SplitType.EQUAL:
        amounts = split_exact(total, len(members), 0)
        return SplitResult(ok=True, amounts=amounts)
    running = Decimal("0")
    amounts: list[Decimal] = []
    for m in members:
        if m.share_value is None or m.share_value <= 0:
            return SplitResult(ok=False, amounts=[], reason="missing_share")
        val = quantize_money(m.share_value)
        amounts.append(val)
        running += val
    if running != total:
        return SplitResult(ok=False, amounts=[], reason="sum_mismatch")
    return SplitResult(ok=True, amounts=amounts)
