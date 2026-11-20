"""Owner-seat behaviour across lists, review, statements, reminders, and transfer."""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.choices import PaymentMethod
from core.money import quantize_money
from dues.models import Due, DueStatus
from notifications.models import Reminder
from notifications.reminders import send_reminders
from plans.models import Subscription
from payments import selectors as payment_selectors
from reports import statement_selectors
from sharing.models import Member

from tests.test_payments import _submit
from tests.test_subscriptions import client_for
from tests.test_transfers import ensure_owner_seat, start_transfer
from tests.test_transfers_matrix import accept


pytestmark = pytest.mark.django_db


def _dues_excluding_owner_seat(charge, sub: Subscription) -> list[Due]:
    return list(Due.objects.filter(charge=charge).exclude(member__user_id=sub.owner_id))


def _collected_expected(dues: list[Due]) -> tuple[Decimal, Decimal]:
    active = [d for d in dues if d.status != DueStatus.WAIVED]
    if not active:
        return Decimal("0"), Decimal("0")
    collected = sum((d.amount_bdt for d in active if d.status == DueStatus.PAID), Decimal("0"))
    expected = sum((d.amount_bdt for d in active), Decimal("0"))
    return quantize_money(collected), quantize_money(expected)


def test_collected_expected_exclude_owner_seat_list_detail_review(world):
    charge = world["charge_x"]
    sub = world["plan_x"]
    owner_m = Member.objects.get(shared_plan=world["shared_x"], user=world["owner"])
    owner_due = Due.objects.get(charge=charge, member=owner_m)
    member_due = world["due_x"]
    owner_due.status = DueStatus.PAID
    owner_due.save(update_fields=["status"])
    member_due.status = DueStatus.DUE
    member_due.save(update_fields=["status"])

    roster = _dues_excluding_owner_seat(charge, sub)
    exp_collected, exp_expected = _collected_expected(roster)

    owner = client_for(world["owner"])
    item = next(x for x in owner.get("/api/subscriptions/").json()["results"] if x["id"] == sub.pk)
    assert Decimal(item["collected"]) == exp_collected
    assert Decimal(item["expected"]) == exp_expected

    detail = owner.get(f"/api/subscriptions/{sub.pk}/").json()
    assert Decimal(detail["collected"]) == exp_collected
    assert Decimal(detail["expected"]) == exp_expected

    review = owner.get(f"/api/shared-plans/{sub.pk}/review/").json()
    assert Decimal(review["confirmed"]["expected"]) == exp_expected


def test_member_reminders_skip_owner_seat_owner_renewal_still_fires(world):
    today = world["charge_x"].due_date
    world["owner"].reminder_days = "0"
    world["owner"].email_reminders = False
    world["owner"].save()
    world["member"].reminder_days = "0"
    world["member"].email_reminders = False
    world["member"].save()

    owner_m = Member.objects.get(shared_plan=world["shared_x"], user=world["owner"])
    owner_due = Due.objects.get(charge=world["charge_x"], member=owner_m)
    owner_due.status = DueStatus.DUE
    owner_due.save(update_fields=["status"])
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])

    Reminder.objects.filter(user__in=[world["owner"], world["member"]]).delete()

    counts = send_reminders(today)
    assert counts["member_reminders"] >= 1
    assert counts["owner_reminders"] >= 1
    assert Reminder.objects.filter(user=world["member"], kind="due_soon").exists()
    assert Reminder.objects.filter(user=world["owner"], kind="renewal").exists()
    assert not Reminder.objects.filter(user=world["owner"], kind="due_soon").exists()


def test_owner_statement_includes_owner_seat_row(world):
    owner_m = Member.objects.get(shared_plan=world["shared_x"], user=world["owner"])
    due = Due.objects.get(charge=world["charge_x"], member=owner_m)
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    oc = client_for(world["owner"])
    assert (
        oc.post(
            f"/api/dues/{due.pk}/mark-paid/",
            {"date": str(world["today"]), "method": PaymentMethod.CASH},
            format="json",
        ).status_code
        == 200
    )
    month = world["charge_x"].period_start.replace(day=1)
    _, ledger_rows = payment_selectors.ledger_build(world["shared_x"], {"month": month})
    assert any(r["member"]["is_owner_seat"] for r in ledger_rows)
    payload = statement_selectors.owner_statement_payload(world["owner"], world["shared_x"], month)
    assert any(row["member_name"] == world["owner"].name for row in payload["rows"])


def test_member_statement_shows_payment_for_owner_seat(world):
    owner_m = Member.objects.get(shared_plan=world["shared_x"], user=world["owner"])
    owner_due = Due.objects.get(charge=world["charge_x"], member=owner_m)
    owner_due.status = DueStatus.DUE
    owner_due.save(update_fields=["status"])
    pay = _submit(client_for(world["member"]), world["plan_x"].pk, [owner_due.pk], transaction_id="STMCOV01")
    assert pay.status_code == 201
    owner_client = client_for(world["owner"])
    assert owner_client.post(f"/api/payments/{pay.json()['payment_id']}/confirm/", {}, format="json").status_code == 200
    month = world["charge_x"].period_start.replace(day=1)
    data = statement_selectors.member_statement_payload(world["member_row"], month)
    assert data["cover_rows"]
    assert any("Covered by" in (row.get("notes") or "") for row in data["cover_rows"])


def test_transfer_accept_leaves_both_seats_due_statuses(world):
    owner_m = Member.objects.get(shared_plan=world["shared_x"], user=world["owner"])
    owner_due = Due.objects.get(charge=world["charge_x"], member=owner_m)
    member_due = world["due_x"]
    owner_due.status = DueStatus.PAID
    owner_due.save(update_fields=["status"])
    member_due.status = DueStatus.PENDING
    member_due.save(update_fields=["status"])
    before = {d.pk: d.status for d in Due.objects.filter(charge__subscription=world["plan_x"])}

    target = ensure_owner_seat(world)
    owner = client_for(world["owner"])
    member = client_for(world["member"])
    tr_id = start_transfer(owner, world["plan_x"].pk, target.pk).json()["id"]
    assert accept(member, tr_id).status_code == 200

    after = {d.pk: d.status for d in Due.objects.filter(charge__subscription=world["plan_x"])}
    assert before == after