"""Pure billing schedule math (no ORM)."""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Sequence

@dataclass(frozen=True)
class Schedule:
    start_date: date
    trial_end_date: date | None
    anchor_day: int
    cycle_unit: str
    cycle_count: int
    renewal_type: str
    end_date: date | None = None
    paused_on: date | None = None
    cancelled_on: date | None = None
    status: str = "active"
    billing_from: date | None = None


def _as_date(value: date | str) -> date:
    if isinstance(value, str):
        return date.fromisoformat(value)
    return value


def first_bill_date(start_date: date, trial_end_date: date | None) -> date:
    start_date = _as_date(start_date)
    if trial_end_date:
        return _as_date(trial_end_date)
    return start_date


def first_renewal_date(schedule: Schedule) -> date:
    """First cycle-end / provider renewal (plan start is not a renewal for non-trial plans)."""
    first = first_bill_date(schedule.start_date, schedule.trial_end_date)
    if schedule.trial_end_date:
        return first
    return nth_due_date(
        first,
        schedule.anchor_day,
        schedule.cycle_unit,
        schedule.cycle_count,
        1,
    )


@dataclass(frozen=True)
class BillingPeriod:
    period_start: date
    due_date: date
    period_end: date


def renewal_k_start(schedule: Schedule) -> int:
    """Index of the first renewal due date (trial end is k=0; otherwise start date is not a renewal)."""
    return 0 if schedule.trial_end_date else 1


def billing_periods_between(schedule: Schedule, from_date: date, to_date: date) -> list[BillingPeriod]:
    """Cycles from plan start: period_start … due_date inclusive; next period starts due_date + 1 day."""
    first = first_bill_date(schedule.start_date, schedule.trial_end_date)
    start_k = renewal_k_start(schedule)
    end_before = stop_date(schedule)
    out: list[BillingPeriod] = []
    k = start_k
    while k < 50000:
        due = nth_due_date(first, schedule.anchor_day, schedule.cycle_unit, schedule.cycle_count, k)
        if end_before is not None and due >= end_before:
            break
        if k == start_k:
            period_start = first
        else:
            period_start = nth_due_date(
                first, schedule.anchor_day, schedule.cycle_unit, schedule.cycle_count, k - 1
            ) + timedelta(days=1)
        period_end = period_end_for(schedule, due)
        if period_start > to_date:
            break
        if period_end >= from_date:
            out.append(BillingPeriod(period_start=period_start, due_date=due, period_end=period_end))
        k += 1
    return out


def _last_day(year: int, month: int) -> int:
    return monthrange(year, month)[1]


def _add_months(year: int, month: int, months: int) -> tuple[int, int]:
    month_index = year * 12 + (month - 1) + months
    return month_index // 12, month_index % 12 + 1


def nth_due_date(first: date, anchor_day: int, unit: str, count: int, k: int) -> date:
    first = _as_date(first)
    if k < 0:
        raise ValueError("k must be non-negative")
    if count < 1:
        raise ValueError("count must be positive")
    if unit == "month":
        y, m = _add_months(first.year, first.month, k * count)
        last = _last_day(y, m)
        return date(y, m, min(anchor_day, last))
    if unit == "year":
        y, m = _add_months(first.year, first.month, k * count * 12)
        last = _last_day(y, m)
        return date(y, m, min(anchor_day, last))
    if unit == "week":
        return first + timedelta(days=7 * k * count)
    if unit == "day":
        return first + timedelta(days=k * count)
    raise ValueError(f"Unknown cycle unit: {unit}")


def schedule_date_counts_for_user(on_date: date, *, today: date, billing_from: date) -> bool:
    """Past renewals always count; future ones only once member billing has started (billing_from)."""
    if on_date < today:
        return True
    return on_date >= billing_from


def stop_date(schedule: Schedule) -> date | None:
    stops: list[date] = []
    if schedule.status == "paused" and schedule.paused_on:
        stops.append(schedule.paused_on)
    if schedule.cancelled_on:
        stops.append(schedule.cancelled_on)
    if schedule.renewal_type == "fixed_term" and schedule.end_date:
        stops.append(schedule.end_date)
    if not stops:
        return None
    return min(stops)


def due_dates_between(schedule: Schedule, from_date: date, to_date: date) -> list[date]:
    """Renewal (cycle-end) dates only — plan start is not a renewal."""
    first = first_bill_date(schedule.start_date, schedule.trial_end_date)
    end_before = stop_date(schedule)
    out: list[date] = []
    k = renewal_k_start(schedule)
    while True:
        due = nth_due_date(first, schedule.anchor_day, schedule.cycle_unit, schedule.cycle_count, k)
        if due > to_date:
            break
        if end_before is not None and due >= end_before:
            break
        if due >= from_date:
            out.append(due)
        k += 1
    return out


def next_due_date(schedule: Schedule, from_date: date) -> date | None:
    """Next renewal on or after from_date (plan start is never returned for non-trial plans)."""
    first = first_bill_date(schedule.start_date, schedule.trial_end_date)
    end_before = stop_date(schedule)
    k = renewal_k_start(schedule)
    while True:
        due = nth_due_date(first, schedule.anchor_day, schedule.cycle_unit, schedule.cycle_count, k)
        if end_before is not None and due >= end_before:
            return None
        if due >= from_date:
            return due
        k += 1
        if k > 50000:
            return None


def period_end_for(schedule: Schedule, due_date: date) -> date:
    """Cycle ends on the renewal date; the following period begins the next calendar day."""
    _ = schedule
    return due_date


def price_at(prices: Sequence[Any], on_date: date) -> Decimal:
    if not prices:
        raise ValueError("prices must not be empty")
    applicable = [p for p in prices if p.effective_from <= on_date]
    if applicable:
        best = max(applicable, key=lambda p: (p.effective_from, getattr(p, "id", 0)))
        return Decimal(best.amount)
    earliest = min(prices, key=lambda p: (p.effective_from, getattr(p, "id", 0)))
    return Decimal(earliest.amount)


def monthly_equivalent(amount: Decimal, unit: str, count: int) -> Decimal:
    amt = Decimal(amount)
    if count < 1:
        raise ValueError("count must be positive")
    if unit == "month":
        value = amt / Decimal(count)
    elif unit == "year":
        value = amt / (Decimal(12) * Decimal(count))
    elif unit == "week":
        value = amt * Decimal(52) / (Decimal(12) * Decimal(count))
    elif unit == "day":
        value = amt * Decimal(365) / (Decimal(12) * Decimal(count))
    else:
        raise ValueError(f"Unknown cycle unit: {unit}")
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _first_on_or_after(
    first: date,
    anchor_day: int,
    unit: str,
    count: int,
    on_or_after: date,
    *,
    start_k: int = 0,
) -> date | None:
    k = start_k
    while True:
        due = nth_due_date(first, anchor_day, unit, count, k)
        if due >= on_or_after:
            return due
        k += 1
        if k > 50000:
            return None


def validate_next_renewal(schedule: Schedule, target: date, today: date) -> bool:
    first = first_bill_date(schedule.start_date, schedule.trial_end_date)
    start_k = renewal_k_start(schedule)
    unit = schedule.cycle_unit
    if unit in ("month", "year"):
        anchor = target.day
        if unit == "year" and target.month != first.month:
            return False
        expected = _first_on_or_after(first, anchor, unit, schedule.cycle_count, today, start_k=start_k)
    else:
        expected = _first_on_or_after(
            first, schedule.anchor_day, unit, schedule.cycle_count, today, start_k=start_k
        )
    return expected is not None and target == expected
