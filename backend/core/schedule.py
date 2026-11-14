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
    """First date a member or owner is charged. Plan start itself is never a due date."""
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
    """Past renewals always count; future ones only on or after billing_from."""
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
    first = first_bill_date(schedule.start_date, schedule.trial_end_date)
    end_before = stop_date(schedule)
    out: list[date] = []
    k = 0
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
    first = first_bill_date(schedule.start_date, schedule.trial_end_date)
    end_before = stop_date(schedule)
    k = 0
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
    first = first_bill_date(schedule.start_date, schedule.trial_end_date)
    k = 0
    while True:
        due = nth_due_date(first, schedule.anchor_day, schedule.cycle_unit, schedule.cycle_count, k)
        if due == due_date:
            nxt = nth_due_date(first, schedule.anchor_day, schedule.cycle_unit, schedule.cycle_count, k + 1)
            return nxt - timedelta(days=1)
        if due > due_date:
            raise ValueError("due_date is not on the billing schedule")
        k += 1


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
) -> date | None:
    k = 0
    while True:
        due = nth_due_date(first, anchor_day, unit, count, k)
        if due >= on_or_after:
            return due
        k += 1
        if k > 50000:
            return None


def validate_next_renewal(schedule: Schedule, target: date, today: date) -> bool:
    first = first_bill_date(schedule.start_date, schedule.trial_end_date)
    unit = schedule.cycle_unit
    if unit in ("month", "year"):
        anchor = target.day
        if unit == "year" and target.month != first.month:
            return False
        expected = _first_on_or_after(first, anchor, unit, schedule.cycle_count, today)
    else:
        expected = _first_on_or_after(first, schedule.anchor_day, unit, schedule.cycle_count, today)
    return expected is not None and target == expected
