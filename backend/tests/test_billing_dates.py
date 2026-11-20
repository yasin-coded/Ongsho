from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from core.schedule import (
    Schedule,
    due_dates_between,
    first_bill_date,
    monthly_equivalent,
    nth_due_date,
    period_end_for,
    price_at,
    validate_next_renewal,
)


def _monthly_schedule(
    start: date,
    *,
    anchor: int | None = None,
    trial_end: date | None = None,
    end_date: date | None = None,
    cancelled_on: date | None = None,
    renewal_type: str = "auto",
    count: int = 1,
) -> Schedule:
    return Schedule(
        start_date=start,
        trial_end_date=trial_end,
        anchor_day=anchor or start.day,
        cycle_unit="month",
        cycle_count=count,
        renewal_type=renewal_type,
        end_date=end_date,
        cancelled_on=cancelled_on,
    )


def _dates(first: date, anchor: int, count: int, n: int, *, unit: str = "month") -> list[date]:
    return [nth_due_date(first, anchor, unit, count, k) for k in range(n)]


def test_monthly_anchor_31_2026():
    first = date(2026, 1, 31)
    got = _dates(first, 31, 1, 12)
    want = [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
        date(2026, 5, 31),
        date(2026, 6, 30),
        date(2026, 7, 31),
        date(2026, 8, 31),
        date(2026, 9, 30),
        date(2026, 10, 31),
        date(2026, 11, 30),
        date(2026, 12, 31),
    ]
    assert got == want


def test_monthly_anchor_31_leap_feb():
    first = date(2028, 1, 31)
    assert _dates(first, 31, 1, 3)[1:3] == [date(2028, 2, 29), date(2028, 3, 31)]


def test_monthly_anchor_30():
    first = date(2026, 1, 30)
    assert _dates(first, 30, 1, 3) == [date(2026, 1, 30), date(2026, 2, 28), date(2026, 3, 30)]


def test_monthly_anchor_29():
    assert _dates(date(2026, 1, 29), 29, 1, 3) == [date(2026, 1, 29), date(2026, 2, 28), date(2026, 3, 29)]
    assert _dates(date(2028, 1, 29), 29, 1, 3) == [date(2028, 1, 29), date(2028, 2, 29), date(2028, 3, 29)]


def test_every_two_months_from_31():
    first = date(2026, 1, 31)
    assert _dates(first, 31, 2, 3) == [date(2026, 1, 31), date(2026, 3, 31), date(2026, 5, 31)]


def test_every_three_months_from_31():
    first = date(2026, 1, 31)
    assert _dates(first, 31, 3, 3) == [date(2026, 1, 31), date(2026, 4, 30), date(2026, 7, 31)]


def test_yearly_leap_anchor():
    first = date(2028, 2, 29)
    assert _dates(first, 29, 1, 5, unit="year") == [
        date(2028, 2, 29),
        date(2029, 2, 28),
        date(2030, 2, 28),
        date(2031, 2, 28),
        date(2032, 2, 29),
    ]


def test_monthly_nov_15_cross_year():
    first = date(2026, 11, 15)
    assert _dates(first, 15, 1, 3) == [date(2026, 11, 15), date(2026, 12, 15), date(2027, 1, 15)]


def test_weekly_and_biweekly():
    first = date(2026, 11, 5)
    assert _dates(first, 5, 1, 3, unit="week") == [date(2026, 11, 5), date(2026, 11, 12), date(2026, 11, 19)]
    assert _dates(first, 5, 2, 2, unit="week") == [date(2026, 11, 5), date(2026, 11, 19)]


def test_every_ten_days():
    first = date(2026, 12, 25)
    assert _dates(first, 25, 10, 2, unit="day") == [date(2026, 12, 25), date(2027, 1, 4)]


def test_trial_first_bill():
    assert first_bill_date(date(2026, 10, 24), date(2026, 11, 7)) == date(2026, 11, 7)
    sch = _monthly_schedule(date(2026, 10, 24), trial_end=date(2026, 11, 7), anchor=7)
    assert due_dates_between(sch, date(2026, 11, 1), date(2026, 12, 31)) == [date(2026, 11, 7), date(2026, 12, 7)]


def test_anchor_reset_to_eight():
    sch = _monthly_schedule(date(2026, 1, 5), anchor=8)
    assert due_dates_between(sch, date(2026, 1, 1), date(2026, 2, 28)) == [date(2026, 1, 8), date(2026, 2, 8)]


def test_fixed_term_excludes_end_charge():
    sch = _monthly_schedule(date(2026, 9, 5), anchor=5, end_date=date(2026, 12, 5), renewal_type="fixed_term")
    assert due_dates_between(sch, date(2026, 9, 1), date(2026, 12, 31)) == [
        date(2026, 10, 5),
        date(2026, 11, 5),
    ]


def test_cancelled_stops_charges():
    sch = _monthly_schedule(date(2026, 9, 5), anchor=5, cancelled_on=date(2026, 12, 5))
    assert due_dates_between(sch, date(2026, 9, 1), date(2027, 1, 1)) == [
        date(2026, 10, 5),
        date(2026, 11, 5),
    ]


def test_period_end_for():
    sch = _monthly_schedule(date(2026, 9, 5), anchor=5)
    assert period_end_for(sch, date(2026, 11, 5)) == date(2026, 12, 4)
    sch31 = _monthly_schedule(date(2026, 1, 31), anchor=31)
    assert period_end_for(sch31, date(2026, 1, 31)) == date(2026, 2, 27)


@dataclass
class _Price:
    effective_from: date
    amount: Decimal
    id: int = 0


def test_price_at():
    prices = [
        _Price(date(2026, 1, 1), Decimal("100")),
        _Price(date(2026, 6, 1), Decimal("120"), id=1),
    ]
    assert price_at(prices, date(2026, 5, 15)) == Decimal("100")
    assert price_at(prices, date(2026, 6, 1)) == Decimal("120")
    assert price_at(prices, date(2025, 12, 31)) == Decimal("100")


@pytest.mark.parametrize(
    "amount,unit,count,want",
    [
        (Decimal("3500"), "year", 1, Decimal("291.67")),
        (Decimal("100"), "week", 1, Decimal("433.33")),
        (Decimal("10"), "day", 10, Decimal("30.42")),
        (Decimal("100"), "month", 2, Decimal("50.00")),
    ],
)
def test_monthly_equivalent(amount, unit, count, want):
    assert monthly_equivalent(amount, unit, count) == want


@pytest.mark.parametrize(
    "target,today,valid",
    [
        (date(2026, 12, 5), date(2026, 11, 9), True),
        (date(2026, 12, 8), date(2026, 11, 9), True),
        (date(2027, 1, 8), date(2026, 11, 9), False),
    ],
)
def test_validate_next_renewal_monthly(target, today, valid):
    sch = _monthly_schedule(date(2026, 6, 5), anchor=5)
    assert validate_next_renewal(sch, target, today) is valid


def test_validate_next_renewal_yearly():
    sch = Schedule(
        start_date=date(2026, 1, 18),
        trial_end_date=None,
        anchor_day=18,
        cycle_unit="year",
        cycle_count=1,
        renewal_type="auto",
    )
    assert validate_next_renewal(sch, date(2027, 1, 18), date(2026, 11, 1)) is True
    assert validate_next_renewal(sch, date(2027, 3, 1), date(2026, 11, 1)) is False


def test_validate_next_renewal_weekly():
    sch = Schedule(
        start_date=date(2026, 11, 5),
        trial_end_date=None,
        anchor_day=5,
        cycle_unit="week",
        cycle_count=1,
        renewal_type="auto",
    )
    assert validate_next_renewal(sch, date(2026, 11, 12), date(2026, 11, 9)) is True
    assert validate_next_renewal(sch, date(2026, 11, 19), date(2026, 11, 9)) is False
