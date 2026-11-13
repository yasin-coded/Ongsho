from __future__ import annotations

import re

from core.exceptions import ValidationFailed

_TID_RE = re.compile(r"^[A-Z0-9-]+$")


def normalize_tid(raw: str | None) -> str:
    return re.sub(r"\s+", "", (raw or "")).upper()


def _luhn_valid(digits: str) -> bool:
    if not digits.isdigit():
        return False
    total = 0
    reverse = digits[::-1]
    for i, ch in enumerate(reverse):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def validate_transaction_id(raw: str | None) -> str:
    tid = normalize_tid(raw)
    if len(tid) < 6:
        raise ValidationFailed(
            "Enter a valid transaction ID.",
            fields={"transaction_id": ["That looks too short. Copy the full ID."]},
        )
    if len(tid) > 64:
        raise ValidationFailed(
            "Enter a valid transaction ID.",
            fields={"transaction_id": ["That ID is too long."]},
        )
    if not _TID_RE.match(tid):
        raise ValidationFailed(
            "Enter a valid transaction ID.",
            fields={"transaction_id": ["Use letters, digits and dashes only."]},
        )
    card_digits = re.sub(r"\D", "", tid)
    if 13 <= len(card_digits) <= 19 and _luhn_valid(card_digits):
        raise ValidationFailed(
            "Enter a payment app transaction ID, not a card number.",
            fields={"transaction_id": ["This looks like a card number. Use your payment app ID."]},
        )
    return tid
