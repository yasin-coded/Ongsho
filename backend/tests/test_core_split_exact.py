from decimal import Decimal

from core.money import split_exact


def test_shares_sum_to_charge_with_leftover_paisa_to_owner():
    total = Decimal("100.00")
    amounts = split_exact(total, 3, leftover_index=0)
    assert sum(amounts, Decimal("0")) == total
    assert amounts[0] == Decimal("33.34")
    assert amounts[1] == amounts[2] == Decimal("33.33")