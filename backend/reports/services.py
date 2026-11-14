"""Write-side business rules for statements and exports."""

from __future__ import annotations

import uuid
from datetime import date

from django.db import IntegrityError, transaction

from audit import services as audit_services
from reports.models import Statement
from reports import pdf as pdf_builders
from reports import statement_selectors
from sharing import selectors as sharing_selectors
from sharing.models import SharedPlan

def _needs_number(stmt: Statement) -> bool:
    return not stmt.number.startswith("ONG-")


def _assign_statement_number(stmt: Statement, shared: SharedPlan, month: date) -> None:
    plan_id = shared.subscription_id
    stmt.number = f"ONG-{month.strftime('%Y%m')}-{plan_id:04d}-{stmt.pk:04d}"
    stmt.save(update_fields=["number"])


@transaction.atomic
def get_or_create_statement(user, shared: SharedPlan, month: date) -> tuple[Statement, bool]:
    stmt = (
        Statement.objects.select_for_update()
        .filter(user=user, shared_plan=shared, month=month)
        .first()
    )
    if stmt:
        if _needs_number(stmt):
            _assign_statement_number(stmt, shared, month)
        return stmt, False
    try:
        stmt = Statement.objects.create(
            user=user,
            shared_plan=shared,
            month=month,
            number=f"TMP-{uuid.uuid4().hex}",
        )
    except IntegrityError:
        stmt = Statement.objects.get(user=user, shared_plan=shared, month=month)
        if _needs_number(stmt):
            _assign_statement_number(stmt, shared, month)
        return stmt, False
    _assign_statement_number(stmt, shared, month)
    return stmt, True


def _audit_first_download(user, shared: SharedPlan, month: date, stmt: Statement) -> None:
    audit_services.log(
        user,
        "statement.downloaded",
        "Statement",
        stmt.pk,
        None,
        None,
        plan_id=shared.subscription_id,
        summary=f"You downloaded the statement for {month:%Y-%m}",
    )


def issue_owner_statement(user, plan_id: int, request, today: date) -> tuple[bytes, Statement]:
    shared = sharing_selectors.shared_plan_for_owner(user, plan_id)
    month = statement_selectors.parse_statement_month_param(request, today)
    data = statement_selectors.owner_statement_payload(user, shared, month)
    stmt, created = get_or_create_statement(user, shared, month)
    data["number"] = stmt.number
    if created:
        _audit_first_download(user, shared, month, stmt)
    return pdf_builders.build_owner_statement(data, compress=True), stmt


def issue_member_statement(user, plan_id: int, request, today: date) -> tuple[bytes, Statement]:
    member = statement_selectors.member_for_statement(user, plan_id)
    month = statement_selectors.parse_statement_month_param(request, today)
    data = statement_selectors.member_statement_payload(member, month)
    stmt, created = get_or_create_statement(user, member.shared_plan, month)
    data["number"] = stmt.number
    if created:
        _audit_first_download(user, member.shared_plan, month, stmt)
    return pdf_builders.build_member_statement(data, compress=True), stmt
