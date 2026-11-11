from django.core.exceptions import ValidationError


def validate_reminder_days(value: str) -> None:
    if value is None or value == "":
        raise ValidationError("Reminder days cannot be empty.")
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if not parts:
        raise ValidationError("Enter at least one reminder day.")
    if len(parts) > 3:
        raise ValidationError("At most three reminder days.")
    seen: set[int] = set()
    for part in parts:
        if not part.isdigit():
            raise ValidationError("Each reminder day must be a whole number.")
        day = int(part)
        if day < 1 or day > 14:
            raise ValidationError("Each reminder day must be between 1 and 14.")
        if day in seen:
            raise ValidationError("Reminder days must not repeat.")
        seen.add(day)


def parse_reminder_days(value: str) -> list[int]:
    validate_reminder_days(value)
    return sorted((int(p.strip()) for p in value.split(",") if p.strip()), reverse=True)


def format_reminder_days(days: list[int]) -> str:
    validate_reminder_days_value_list(days)
    return ",".join(str(d) for d in days)


def validate_reminder_days_value_list(days: list) -> None:
    if not isinstance(days, list) or not days:
        raise ValidationError("Enter at least one reminder day.")
    if len(days) > 3:
        raise ValidationError("At most three reminder days.")
    seen: set[int] = set()
    for day in days:
        if not isinstance(day, int) or isinstance(day, bool):
            raise ValidationError("Each reminder day must be a whole number.")
        if day < 1 or day > 14:
            raise ValidationError("Each reminder day must be between 1 and 14.")
        if day in seen:
            raise ValidationError("Reminder days must not repeat.")
        seen.add(day)
