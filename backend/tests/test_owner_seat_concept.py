"""Owner seat under the new concept: due by default, ordinary recalculation rules."""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.choices import PaymentMethod
from dues.models import Due, DueStatus
from dues import services as dues_services
from plans.models import PlanMode

from tests.test_subscriptions import client_for, plan_payload


@pytest.mark.django_db
def test_owner_seat_created_as_due(world):
    charge = world["charge_x"]
    owner_row = world["shared_x"].members.get(user=world["owner"])
    due = Due.objects.get(charge=charge, member=owner_row)
    assert due.status == DueStatus.DUE


@pytest.mark.django_db
def test_owner_marks_own_seat_paid_without_proof(world):
    charge = world["charge_x"]
    owner_row = world["shared_x"].members.get(user=world["owner"])
    due = Due.objects.get(charge=charge, member=owner_row)
    client = client_for(world["owner"])
    r = client.post(
        f"/api/dues/{due.pk}/mark-paid/",
        {"date": str(world["today"]), "method": PaymentMethod.CASH},
        format="json",
    )
    assert r.status_code == 200
    due.refresh_from_db()
    assert due.status == DueStatus.PAID


@pytest.mark.django_db
def test_recalculate_changes_owner_amount_only_while_due(world):
    charge = world["charge_x"]
    charge.locked = False
    charge.save(update_fields=["locked"])
    owner_row = world["shared_x"].members.get(user=world["owner"])
    owner_due = Due.objects.get(charge=charge, member=owner_row)
    owner_due.status = DueStatus.DUE
    owner_due.amount_bdt = Decimal("1.00")
    owner_due.save()
    dues_services.recalculate_dues(charge, world["today"], force=True)
    owner_due.refresh_from_db()
    assert owner_due.amount_bdt != Decimal("1.00")
    owner_due.status = DueStatus.PAID
    owner_due.amount_bdt = Decimal("1.00")
    owner_due.save()
    dues_services.recalculate_dues(charge, world["today"], force=True)
    owner_due.refresh_from_db()
    assert owner_due.amount_bdt == Decimal("1.00")


@pytest.mark.django_db
def test_reseller_plan_has_no_owner_seat(world):
    client = client_for(world["owner"])
    r = client.post(
        "/api/subscriptions/",
        {**plan_payload(plan_name="R-No-Owner", plan_mode=PlanMode.RESELLER), "seats": 2},
        format="json",
    )
    assert r.status_code == 201
    from sharing.models import SharedPlan

    shared = SharedPlan.objects.get(subscription_id=r.json()["id"])
    assert not shared.members.filter(user=world["owner"]).exists()