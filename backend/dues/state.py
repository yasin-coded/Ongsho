from __future__ import annotations

from audit import services as audit_services
from core.exceptions import ConflictError
from dues.models import Due, DueStatus

_ALLOWED: set[tuple[str, str]] = {
    (DueStatus.DUE, DueStatus.PENDING),
    (DueStatus.DUE, DueStatus.PAID),
    (DueStatus.DUE, DueStatus.WAIVED),
    (DueStatus.PENDING, DueStatus.PAID),
    (DueStatus.PENDING, DueStatus.DUE),
    (DueStatus.PENDING, DueStatus.WAIVED),
    (DueStatus.PAID, DueStatus.DUE),
    (DueStatus.WAIVED, DueStatus.DUE),
}


def transition(
    due: Due,
    to: str,
    actor,
    *,
    waiver_note: str = "",
    rejection_reason: str = "",
) -> Due:
    from_status = due.status
    if (from_status, to) not in _ALLOWED:
        raise ConflictError(
            f"Cannot change due from {from_status} to {to}.",
            code="invalid_due_status",
        )
    old = {"status": from_status}
    due.status = to
    update_fields = ["status"]
    if to == DueStatus.WAIVED and waiver_note:
        due.waiver_note = waiver_note
        update_fields.append("waiver_note")
    if to == DueStatus.DUE and rejection_reason:
        due.rejection_reason = rejection_reason
        update_fields.append("rejection_reason")
    due.save(update_fields=update_fields)
    plan_id = due.charge.subscription_id
    audit_services.log(actor, "due_status", "Due", due.pk, old, {"status": to}, plan_id=plan_id, summary="")
    return due
