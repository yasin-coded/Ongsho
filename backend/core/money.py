from decimal import Decimal, ROUND_HALF_UP

MONEY_QUANTIZE = Decimal("0.01")
RATE_QUANTIZE = Decimal("0.0001")


def quantize_money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(MONEY_QUANTIZE, rounding=ROUND_HALF_UP)


def to_bdt(amount: Decimal, rate: Decimal) -> Decimal:
    return quantize_money(Decimal(amount) * Decimal(rate))
