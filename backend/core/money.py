from decimal import Decimal, ROUND_HALF_UP

MONEY_QUANTIZE = Decimal("0.01")
RATE_QUANTIZE = Decimal("0.0001")


def quantize_money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(MONEY_QUANTIZE, rounding=ROUND_HALF_UP)


def to_bdt(amount: Decimal, rate: Decimal) -> Decimal:
    return quantize_money(Decimal(amount) * Decimal(rate))


def format_bdt(value: Decimal) -> str:
    """Format a BDT amount as ৳1,200.00 (Unicode minus for negatives)."""
    amount = quantize_money(Decimal(value))
    if amount < 0:
        body = f"{abs(amount):,.2f}"
        return f"৳−{body}"
    return f"৳{amount:,.2f}"
