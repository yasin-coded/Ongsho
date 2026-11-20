"""Owner seat: member pays, IOU, mark-paid, set-due, reminders, transfer statuses."""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.choices import PaymentMethod
from dues.models import Due, DueStatus
from payments.models import Payment, ReviewStatus
from sharing.models import Member

from tests.test_payments import _submit
from tests.test_subscriptions import client_for

pytestmark = pytest.mark.django_db


def test_member_pays_owner_seat_coverable_confirm_iou(world):
    charge = world["charge_x"]
    owner_m = Member.objects.get(shared_plan=world["shared_x"], user=world["owner"])
    owner_due = Due.objects.get(charge=charge, member=owner_m)
    owner_due.status = DueStatus.DUE
    owner_due.save(update_fields=["status"])
    member_client = client_for(world["member"])
    cover = member_client.get(f"/api/me/shared-plans/{world['plan_x'].pk}/").json()
    ids = {row["due_id"] for row in cover["coverable"]}
    assert owner_due.pk in ids
    pay = _submit(member_client, world["plan_x"].pk, [owner_due.pk], transaction_id="OWNIU001")
    assert pay.status_code == 201
    owner_client = client_for(world["owner"])
    pid = pay.json()["payment_id"]
    assert owner_client.post(f"/api/payments/{pid}/confirm/", {}, format="json").status_code == 200
    owner_due.refresh_from_db()
    assert owner_due.status == DueStatus.PAID
    ious = owner_client.get(f"/api/shared-plans/{world['plan_x'].pk}/ious/").json()
    owner_m = Member.objects.get(shared_plan=world["shared_x"], user=world["owner"])
    assert any(i["debtor"]["id"] == owner_m.pk for i in ious)
    assert owner_client.post(f"/api/payments/{pid}/reverse/", {}, format="json").status_code == 200
    owner_due.refresh_from_db()
    assert owner_due.status == DueStatus.DUE


def test_owner_mark_paid_and_set_due(world):
    owner_m = Member.objects.get(shared_plan=world["shared_x"], user=world["owner"])
    due = Due.objects.get(charge=world["charge_x"], member=owner_m)
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    oc = client_for(world["owner"])
    assert (
        oc.post(
            f"/api/dues/{due.pk}/mark-paid/",
            {"date": str(world["today"]), "method": "cash"},
            format="json",
        ).status_code
        == 200
    )
    due.refresh_from_db()
    assert due.status == DueStatus.PAID
    assert oc.post(f"/api/dues/{due.pk}/set-due/", {}, format="json").status_code == 200
    due.refresh_from_db()
    assert due.status == DueStatus.DUE