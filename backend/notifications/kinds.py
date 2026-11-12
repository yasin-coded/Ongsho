"""Notification kind registry — single source of truth for kinds and filter groups."""

PAYMENT_KINDS = frozenset(
    {
        "payment_submitted",
        "payment_confirmed",
        "payment_rejected",
        "payment_reversed",
        "payment_recorded",
        "due_waived",
    }
)

REMINDER_KINDS = frozenset(
    {
        "due_soon",
        "renewal",
        "trial_end",
        "expiry",
    }
)

PLAN_KINDS = frozenset(
    {
        "invite",
        "invite_accepted",
        "invite_declined",
        "leave_request",
        "leave_result",
        "transfer",
        "transfer_result",
        "plan_deleted",
        "price_change",
        "amount_changed",
        "member_removed",
    }
)

ACCOUNT_KINDS = frozenset({"email_changed"})

ALL_KINDS = PAYMENT_KINDS | REMINDER_KINDS | PLAN_KINDS | ACCOUNT_KINDS

KIND_TO_GROUP: dict[str, str] = {}
for _kind in PAYMENT_KINDS:
    KIND_TO_GROUP[_kind] = "payments"
for _kind in REMINDER_KINDS:
    KIND_TO_GROUP[_kind] = "reminders"
for _kind in PLAN_KINDS:
    KIND_TO_GROUP[_kind] = "plans"
for _kind in ACCOUNT_KINDS:
    KIND_TO_GROUP[_kind] = "account"

GROUP_LABELS = frozenset({"payments", "reminders", "plans", "account"})


def group_of(kind: str) -> str:
    try:
        return KIND_TO_GROUP[kind]
    except KeyError:
        raise ValueError(f"Unknown notification kind: {kind!r}")


def validate_kind(kind: str) -> None:
    group_of(kind)
