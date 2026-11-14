"""User-scoped statement data for PDF exports."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.utils import timezone

from core.choices import PaymentMethod
from core.exceptions import NotFound, ValidationFailed
from core.money import quantize_money
from dues.models import DueStatus
from payments import selectors as payment_selectors
from sharing.models import Member, MemberStatus, SharedPlan

_STATEMENT_MEMBER_STATUSES = (
    MemberStatus.ACTIVE,
    MemberStatus.LEAVE_REQUESTED,
    MemberStatus.LEFT,
)


def parse_statement_month_param(request, today: date) -> date:
    raw = request.query_params.get("month")
    if raw in (None, ""):
        raise ValidationFailed(
            "Month is required.",
            fields={"month": ["This field is required."]},
        )
    try:
        parts = raw.split("-")
        year, month = int(parts[0]), int(parts[1])
        if not (1 <= month <= 12):
            raise ValueError
        month_start = date(year, month, 1)
    except (ValueError, IndexError):
        raise ValidationFailed("Invalid month.", fields={"month": ["Use YYYY-MM."]})
    current = date(today.year, today.month, 1)
    if month_start > current:
        raise ValidationFailed(
            "Month cannot be in the future.",
            fields={"month": ["Cannot be in the future."]},
        )
    return month_start


def member_for_statement(user, plan_id: int) -> Member:
    member = (
        Member.objects.select_related("shared_plan__subscription", "user")
        .filter(
            user=user,
            shared_plan__subscription_id=plan_id,
            shared_plan__subscription__archived_on__isnull=True,
            status__in=_STATEMENT_MEMBER_STATUSES,
        )
        .first()
    )
    if member is None:
        raise NotFound("Not found.")
    if member.shared_plan.subscription.owner_id == user.pk:
        raise NotFound("Not found.")
    return member


def _method_label(method: str | None) -> str:
    if method in (None, ""):
        return "—"
    try:
        return PaymentMethod(method).label
    except ValueError:
        return method


def _status_label(status: str) -> str:
    try:
        return DueStatus(status).label
    except ValueError:
        return status


def _row_notes(row: dict) -> str:
    parts: list[str] = []
    if row.get("recorded_by_owner"):
        parts.append("Recorded by owner")
    covered = row.get("covered_by")
    if covered:
        parts.append(f"Covered by {covered}")
    return "; ".join(parts) if parts else "—"


def _pdf_row(row: dict) -> dict:
    return {
        "member_name": row["member"]["name"],
        "amount": row["amount"],
        "status": _status_label(row["status"]),
        "method": _method_label(row.get("method")),
        "transaction_id": row.get("transaction_id") or "—",
        "paid_on": row.get("paid_on") or "—",
        "notes": _row_notes(row),
    }


def cover_rows_for_member(shared: SharedPlan, member: Member, month: date) -> list[dict]:
    key = month.strftime("%Y-%m")
    dues = [
        d
        for d in payment_selectors.plan_dues_for_ledger(shared)
        if d.charge.period_start.strftime("%Y-%m") == key and d.member_id != member.pk
    ]
    alloc_map = payment_selectors.settling_allocations_for_dues([d.pk for d in dues])
    rows: list[dict] = []
    for due in dues:
        alloc = alloc_map.get(due.pk)
        if alloc is None or alloc.payment.member_id != member.pk:
            continue
        rows.append(payment_selectors._ledger_row(due, alloc, shared))
    rows.sort(key=lambda r: (r["member"]["name"].lower(), r["due_date"]))
    return rows


def member_total_paid(own_rows: list[dict], cover_rows: list[dict]) -> str:
    total = Decimal("0")
    for row in own_rows + cover_rows:
        if row["status"] == DueStatus.PAID:
            total += Decimal(row["amount"])
    return str(quantize_money(total))


def _generated_at_label() -> str:
    return timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M %Z")


def owner_statement_payload(user, shared: SharedPlan, month: date) -> dict:
    sub = shared.subscription
    params = {"month": month}
    _all, filtered = payment_selectors.ledger_build(shared, params)
    if not filtered:
        raise ValidationFailed(
            "Nothing to report for this month.",
            code="nothing_to_report",
            fields={"month": ["Nothing to report for this month."]},
        )
    return {
        "number": "",
        "brand": "Ongsho",
        "plan_name": sub.plan_name,
        "month": month.strftime("%Y-%m"),
        "month_label": month.strftime("%B %Y"),
        "generated_at": _generated_at_label(),
        "viewer_name": user.name or "",
        "rows": [_pdf_row(r) for r in filtered],
        "totals": payment_selectors.ledger_totals(filtered),
        "ious": payment_selectors.plan_ious_owner(shared),
        "footer": (
            "Payments happen outside Ongsho. This statement is a record, not a receipt "
            "from the provider or a payment confirmation."
        ),
    }


def member_statement_payload(member: Member, month: date) -> dict:
    shared = member.shared_plan
    sub = shared.subscription
    params = {"month": month, "member": member.pk}
    _all, own_filtered = payment_selectors.ledger_build(shared, params)
    cover = cover_rows_for_member(shared, member, month)
    if not own_filtered and not cover:
        raise ValidationFailed(
            "Nothing to report for this month.",
            code="nothing_to_report",
            fields={"month": ["Nothing to report for this month."]},
        )
    return {
        "number": "",
        "brand": "Ongsho",
        "plan_name": sub.plan_name,
        "month": month.strftime("%Y-%m"),
        "month_label": month.strftime("%B %Y"),
        "generated_at": _generated_at_label(),
        "viewer_name": member.user.name or "",
        "own_rows": [_pdf_row(r) for r in own_filtered],
        "cover_rows": [_pdf_row(r) for r in cover],
        "total_paid": member_total_paid(own_filtered, cover),
        "ious": payment_selectors.plan_ious_member(shared, member),
        "footer": (
            "Payments happen outside Ongsho. This statement is a record, not a receipt "
            "from the provider or a payment confirmation."
        ),
    }
