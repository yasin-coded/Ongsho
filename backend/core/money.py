from decimal import Decimal, ROUND_HALF_UP

MONEY_QUANTIZE = Decimal("0.01")
RATE_QUANTIZE = Decimal("0.0001")


def quantize_money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(MONEY_QUANTIZE, rounding=ROUND_HALF_UP)


def to_bdt(amount: Decimal, rate: Decimal) -> Decimal:
    return quantize_money(Decimal(amount) * Decimal(rate))


def split_exact(total: Decimal, n: int, leftover_index: int = 0) -> list[Decimal]:
    """Split *total* (BDT) into *n* equal shares in whole paisa; remainder goes to *leftover_index*."""
    if n < 1:
        raise ValueError("n must be at least 1")
    amount = quantize_money(Decimal(total))
    total_paisa = int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))
    base = total_paisa // n
    rem = total_paisa % n
    if leftover_index < 0 or leftover_index >= n:
        raise ValueError("leftover_index out of range")
    shares_paisa = [base] * n
    shares_paisa[leftover_index] += rem
    return [quantize_money(Decimal(p) / 100) for p in shares_paisa]


def format_bdt(value: Decimal) -> str:
    """Format a BDT amount as ৳1,200.00 (Unicode minus for negatives)."""
    amount = quantize_money(Decimal(value))
    if amount < 0:
        body = f"{abs(amount):,.2f}"
        return f"৳−{body}"
    return f"৳{amount:,.2f}"
