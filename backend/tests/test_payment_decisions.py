import pytest
from django.contrib.auth import get_user_model
from notifications.models import Notification
from payments.models import Payment, PaymentAllocation, ReviewStatus

from audit.models import AuditLog
from core.choices import PaymentMethod
from dues.models import Due, DueStatus
from tests.test_subscriptions import client_for

User = get_user_model()


def _submit(member_client, plan_id, due_id, tid="DECIDE01"):
    return member_client.post(
        "/api/payments/",
        {
            "plan_id": plan_id,
            "due_ids": [due_id],
            "method": PaymentMethod.BKASH,
            "transaction_id": tid,
        },
        format="json",
    )


@pytest.mark.django_db
def test_confirm_and_notify_payer(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    member = client_for(world["member"])
    owner = client_for(world["owner"])
    pay_id = _submit(member, world["plan_x"].pk, due.pk).json()["payment_id"]
    note = Notification.objects.filter(user=world["owner"], kind="payment_submitted").latest("id")
    r = owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    assert r.status_code == 200
    assert "covered" in r.json()["message"].lower()
    due.refresh_from_db()
    assert due.status == DueStatus.PAID
    assert Notification.objects.filter(user=world["member"], kind="payment_confirmed").exists()
    body = owner.get("/api/notifications/").json()
    resolved = next(x for x in body["results"] if x["id"] == note.id)
    assert resolved.get("resolved") in ("approved", None)


@pytest.mark.django_db
def test_confirm_twice_409(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    member = client_for(world["member"])
    owner = client_for(world["owner"])
    pay_id = _submit(member, world["plan_x"].pk, due.pk, tid="CONF2X01").json()["payment_id"]
    assert owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json").status_code == 200
    assert owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json").status_code == 409


@pytest.mark.django_db
def test_reject_requires_reason(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    pay_id = _submit(client_for(world["member"]), world["plan_x"].pk, due.pk, tid="REJ01XXX").json()["payment_id"]
    owner = client_for(world["owner"])
    assert owner.post(f"/api/payments/{pay_id}/reject/", {}, format="json").status_code == 400
    r = owner.post(f"/api/payments/{pay_id}/reject/", {"reason": "Wrong ID"}, format="json")
    assert r.status_code == 200
    due.refresh_from_db()
    assert due.status == DueStatus.DUE
    assert due.rejection_reason == "Wrong ID"


@pytest.mark.django_db
def test_member_cannot_mark_due_paid(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    member = client_for(world["member"])
    r = member.post(
        f"/api/dues/{due.pk}/mark-paid/",
        {"date": str(world["today"]), "method": PaymentMethod.CASH, "note": "x"},
        format="json",
    )
    assert r.status_code == 404
    due.refresh_from_db()
    assert due.status == DueStatus.DUE


@pytest.mark.django_db
def test_owner_mark_paid_member_due_no_transaction_id(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    owner = client_for(world["owner"])
    r = owner.post(
        f"/api/dues/{due.pk}/mark-paid/",
        {"date": str(world["today"]), "method": PaymentMethod.CASH, "note": "cash"},
        format="json",
    )
    assert r.status_code == 200
    due.refresh_from_db()
    assert due.status == DueStatus.PAID
    payment = Payment.objects.get(
        member=due.member,
        review_status=ReviewStatus.CONFIRMED,
    )
    assert payment.transaction_id is None
    assert payment.recorded_by_id == world["owner"].pk
    assert PaymentAllocation.objects.filter(payment=payment, due=due).exists()
    assert AuditLog.objects.filter(action="due.mark_paid", entity_id=due.pk).exists()
    assert Notification.objects.filter(user=world["member"], kind="payment_recorded").exists()


@pytest.mark.django_db
def test_mark_paid_on_pending(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    pay_id = _submit(client_for(world["member"]), world["plan_x"].pk, due.pk, tid="MKPEND01").json()["payment_id"]
    owner = client_for(world["owner"])
    today = world["today"]
    r = owner.post(
        f"/api/dues/{due.pk}/mark-paid/",
        {"date": str(today), "method": PaymentMethod.CASH, "note": "cash"},
        format="json",
    )
    assert r.status_code == 200
    due.refresh_from_db()
    assert due.status == DueStatus.PAID
    assert Payment.objects.get(pk=pay_id).review_status == ReviewStatus.REJECTED


@pytest.mark.django_db
def test_waive_due(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    owner = client_for(world["owner"])
    r = owner.post(f"/api/dues/{due.pk}/waive/", {"note": "birthday"}, format="json")
    assert r.status_code == 200
    due.refresh_from_db()
    assert due.status == DueStatus.WAIVED
    assert "birthday" in due.waiver_note


@pytest.mark.django_db
def test_set_due_on_waived(world):
    due = world["due_x"]
    due.status = DueStatus.WAIVED
    due.save(update_fields=["status"])
    owner = client_for(world["owner"])
    assert owner.post(f"/api/dues/{due.pk}/set-due/", {}, format="json").status_code == 200
    assert Due.objects.get(pk=due.pk).status == DueStatus.DUE


@pytest.mark.django_db
def test_member_cannot_confirm(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    pay_id = _submit(client_for(world["member"]), world["plan_x"].pk, due.pk, tid="MEMCONF1").json()["payment_id"]
    assert client_for(world["member"]).post(f"/api/payments/{pay_id}/confirm/", {}, format="json").status_code == 404


@pytest.mark.django_db
def test_audit_on_confirm(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    pay_id = _submit(client_for(world["member"]), world["plan_x"].pk, due.pk, tid="AUDIT001").json()["payment_id"]
    client_for(world["owner"]).post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    row = AuditLog.objects.filter(action="payment.confirmed", plan_id=world["plan_x"].pk).latest("id")
    assert row.summary
    assert row.plan_id == world["plan_x"].pk
