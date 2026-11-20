from decimal import Decimal

import pytest

from core.money import format_bdt


@pytest.mark.parametrize(
    "value,expected",
    [
        (Decimal("0"), "৳0.00"),
        (Decimal("300"), "৳300.00"),
        (Decimal("1200.5"), "৳1,200.50"),
        (Decimal("1234567.89"), "৳1,234,567.89"),
        (Decimal("-10.5"), "৳−10.50"),
    ],
)
def test_format_bdt(value, expected):
    assert format_bdt(value) == expected
