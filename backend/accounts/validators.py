from django.core.exceptions import ValidationError

ALLOWED_REMINDER_DAYS = frozenset({0, 1, 3, 7})


def validate_reminder_days(value: str) -> None:
    if value is None:
        raise ValidationError("Reminder days cannot be null.")
    if value.strip() == "":
        return
    parts = [p.strip() for p in value.split(",") if p.strip()]
    seen: set[int] = set()
    for part in parts:
        try:
            day = int(part)
        except ValueError:
            raise ValidationError("Each reminder day must be one of 0, 1, 3, or 7.")
        if day not in ALLOWED_REMINDER_DAYS:
            raise ValidationError("Each reminder day must be one of 0, 1, 3, or 7.")
        if day in seen:
            raise ValidationError("Reminder days must not repeat.")
        seen.add(day)


def parse_reminder_days(value: str) -> list[int]:
    if value is None or value.strip() == "":
        return []
    validate_reminder_days(value)
    return sorted((int(p.strip()) for p in value.split(",") if p.strip()), reverse=True)


def format_reminder_days(days: list[int]) -> str:
    validate_reminder_days_value_list(days)
    if not days:
        return ""
    return ",".join(str(d) for d in sorted(days, reverse=True))


def validate_reminder_days_value_list(days) -> None:
    if not isinstance(days, list):
        raise ValidationError("days_before must be a list.")
    seen: set[int] = set()
    for day in days:
        if not isinstance(day, int) or isinstance(day, bool):
            raise ValidationError("Each reminder day must be one of 0, 1, 3, or 7.")
        if day not in ALLOWED_REMINDER_DAYS:
            raise ValidationError("Each reminder day must be one of 0, 1, 3, or 7.")
        if day in seen:
            raise ValidationError("Reminder days must not repeat.")
        seen.add(day)
