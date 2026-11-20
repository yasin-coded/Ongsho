"""Part C: POST /api/payments/{id}/waive/."""

from __future__ import annotations

import pytest
from audit.models import AuditLog
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from core.choices import PaymentMethod
from dues.models import Due, DueStatus
from notifications.models import Notification
from payments.models import Payment, PaymentAllocation, ReviewStatus

from tests.test_payments import TID, _submit
from tests.test_subscriptions import assert_error_shape, client_for

User = get_user_model()


def _waive(client, payment_id, note="Owner note"):
    return client.post(f"/api/payments/{payment_id}/waive/", {"note": note}, format="json")


@pytest.mark.django_db
def test_payment_waive_single_due(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    member = client_for(world["member"])
    pay_id = _submit(member, world["plan_x"].pk, [due.pk]).json()["payment_id"]
    owner = client_for(world["owner"])
    r = _waive(owner, pay_id)
    assert r.status_code == 200
    assert r.json()["message"] == "Waived. Nothing is owed for those dues now."
    due.refresh_from_db()
    assert due.status == DueStatus.WAIVED
    assert due.waiver_note == "Owner note"
    pay = Payment.objects.get(pk=pay_id)
    assert pay.review_status == ReviewStatus.REJECTED
    assert pay.reviewed_at is not None
    assert Notification.objects.filter(user=world["member"], kind="due_waived").exists()
    assert AuditLog.objects.filter(plan_id=world["plan_x"].pk, summary__icontains="waived").exists()


@pytest.mark.django_db
def test_payment_waive_multi_due(world_rich):
    world = world_rich
    charge = world["charge_x"]
    dues = list(Due.objects.filter(charge=charge).exclude(member__user=world["owner"]))
    assert len(dues) >= 2, "fixture must provide two non-owner dues on the charge"
    due_ids = [d.pk for d in dues[:2]]
    for d in dues[:2]:
        d.status = DueStatus.DUE
        d.save(update_fields=["status"])
    member = client_for(world["member"])
    pay_id = _submit(member, world["plan_x"].pk, due_ids).json()["payment_id"]
    r = _waive(client_for(world["owner"]), pay_id, note="Both waived")
    assert r.status_code == 200
    for did in due_ids:
        assert Due.objects.get(pk=did).status == DueStatus.WAIVED


@pytest.mark.django_db
def test_payment_waive_missing_note_400(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    pay_id = _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk]).json()["payment_id"]
    r = _waive(client_for(world["owner"]), pay_id, note="   ")
    assert r.status_code == 400
    assert_error_shape(r)
    assert r.json()["error"]["fields"]["note"]


@pytest.mark.django_db
def test_payment_waive_not_pending_409(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    pay_id = _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk]).json()["payment_id"]
    client_for(world["owner"]).post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    r = _waive(client_for(world["owner"]), pay_id)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "already_decided"


@pytest.mark.django_db
def test_payment_waive_member_and_outsider_404(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    pay_id = _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk]).json()["payment_id"]
    assert _waive(client_for(world["member"]), pay_id).status_code == 404
    assert _waive(client_for(world["outsider"]), pay_id).status_code == 404


@pytest.mark.django_db
def test_payment_waive_resolves_owner_notification(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    pay_id = _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk]).json()["payment_id"]
    note = Notification.objects.filter(user=world["owner"], kind="payment_submitted").first()
    assert note is not None
    _waive(client_for(world["owner"]), pay_id)
    listed = client_for(world["owner"]).get("/api/notifications/").json()
    items = listed if isinstance(listed, list) else listed.get("results", listed.get("items", []))
    match = next((x for x in items if x.get("id") == note.pk), None)
    if match is None:
        gone = client_for(world["owner"]).get(f"/api/notifications/{note.pk}/").json()
        assert gone.get("resolved") is not None
    else:
        assert match.get("resolved") is not None


@pytest.mark.django_db
def test_payment_waive_anonymous_401():
    assert APIClient().post("/api/payments/1/waive/", {}, format="json").status_code == 401
