from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from audit.models import AuditLog


def _json_safe(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def log(
    actor,
    action: str,
    entity_type: str,
    entity_id: int,
    old,
    new,
    *,
    plan_id: int | None = None,
    summary: str = "",
    amount: Decimal | None = None,
) -> AuditLog:
    return AuditLog.objects.create(
        user=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=_json_safe(old),
        new_value=_json_safe(new),
        plan_id=plan_id,
        summary=summary,
        amount=amount,
    )
