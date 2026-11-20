from decimal import Decimal
from types import SimpleNamespace

import pytest

from core.money import quantize_money, split_exact
from dues.splitting import split_charge
from sharing.models import SplitType


@pytest.mark.parametrize(
    "total,n",
    [
        (Decimal("100.00"), 3),
        (Decimal("0.05"), 3),
        (Decimal("1200.00"), 4),
    ],
)
def test_split_exact_sums_to_total(total, n):
    parts = split_exact(total, n, 0)
    assert len(parts) == n
    assert sum(parts, Decimal("0")) == quantize_money(total)


def test_split_exact_leftover_on_index():
    parts = split_exact(Decimal("100.00"), 3, 0)
    assert parts[0] == Decimal("33.34")
    assert parts[1] == Decimal("33.33")
    assert parts[2] == Decimal("33.33")


def test_custom_split_blocked_when_sum_wrong(db):
    shared = SimpleNamespace(split_type=SplitType.CUSTOM)
    members = [
        SimpleNamespace(share_value=Decimal("40.00")),
        SimpleNamespace(share_value=Decimal("40.00")),
    ]
    result = split_charge(shared, members, Decimal("100.00"))
    assert not result.ok


def test_custom_split_ok(db):
    shared = SimpleNamespace(split_type=SplitType.CUSTOM)
    members = [
        SimpleNamespace(share_value=Decimal("60.00")),
        SimpleNamespace(share_value=Decimal("40.00")),
    ]
    result = split_charge(shared, members, Decimal("100.00"))
    assert result.ok
    assert result.amounts == [Decimal("60.00"), Decimal("40.00")]
