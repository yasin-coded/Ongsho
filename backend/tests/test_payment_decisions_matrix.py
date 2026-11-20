"""Owner payment decision API matrix."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from notifications.models import Notification
from payments.models import Payment, PaymentAllocation, ReviewStatus

from audit.models import AuditLog
from billing.models import Charge
from core.choices import PaymentMethod
from dues.models import Due, DueStatus
from sharing.models import Member
from tests.helpers import run_concurrently
from tests.test_payments import _submit
from tests.test_subscriptions import assert_error_shape, client_for

User = get_user_model()


def _open(due):
    due.status = DueStatus.DUE
    due.rejection_reason = ""
    due.save(update_fields=["status", "rejection_reason"])


def _audit_count(plan_id: int) -> int:
    return AuditLog.objects.filter(plan_id=plan_id).exclude(summary="").count()


def _two_member_dues(world):
    charges = list(Charge.objects.filter(subscription=world["plan_x"]).order_by("period_start"))
    assert len(charges) >= 2, "fixture must provide two billing periods on plan_x"
    d1 = Due.objects.get(charge=charges[0], member=world["member_row"])
    d2 = Due.objects.get(charge=charges[-1], member=world["member_row"])
    _open(d1)
    _open(d2)
    return d1, d2


@pytest.mark.django_db
def test_confirm_second_409(world):
    due = world["due_x"]
    _open(due)
    owner = client_for(world["owner"])
    pay_id = _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk], transaction_id="CONF4091").json()[
        "payment_id"
    ]
    assert owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json").status_code == 200
    r = owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "already_decided"


@pytest.mark.django_db(transaction=True)
def test_concurrent_confirm_once(world):
    due = world["due_x"]
    _open(due)
    owner = client_for(world["owner"])
    pay_id = _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk], transaction_id="CONCONF1").json()["payment_id"]

    def confirm():
        return owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json").status_code

    results, _ = run_concurrently([confirm, confirm])
    assert Payment.objects.get(pk=pay_id).review_status == ReviewStatus.CONFIRMED
    assert results.count(200) == 1
    assert 409 in results


@pytest.mark.django_db
def test_confirm_covered_months_message(world_rich):
    world = world_rich
    d1, d2 = _two_member_dues(world)
    owner = client_for(world["owner"])
    pay_id = _submit(
        client_for(world["member"]), world["plan_x"].pk, [d1.pk, d2.pk], transaction_id="TWOMTH01"
    ).json()["payment_id"]
    r = owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    assert r.status_code == 200
    m1 = d1.charge.period_start.strftime("%B")
    m2 = d2.charge.period_start.strftime("%B")
    msg = r.json()["message"].lower()
    assert m1.lower() in msg and m2.lower() in msg
    assert " and " in r.json()["message"]


@pytest.mark.django_db
def test_confirm_notifies_payer(world):
    due = world["due_x"]
    _open(due)
    pay_id = _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk], transaction_id="PAYNOT01").json()["payment_id"]
    client_for(world["owner"]).post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    assert Notification.objects.filter(user=world["member"], kind="payment_confirmed").exists()


@pytest.mark.django_db
def test_confirm_resolves_owner_notification(world):
    due = world["due_x"]
    _open(due)
    pay_id = _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk], transaction_id="RESNOT01").json()["payment_id"]
    owner = client_for(world["owner"])
    note = Notification.objects.filter(user=world["owner"], kind="payment_submitted").latest("id")
    owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    row = next(x for x in owner.get("/api/notifications/").json()["results"] if x["id"] == note.id)
    assert row["resolved"] == "approved"


@pytest.mark.django_db
def test_reject_requires_reason(world):
    due = world["due_x"]
    _open(due)
    owner = client_for(world["owner"])
    pay_id = _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk], transaction_id="REJREQ01").json()["payment_id"]
    before = _audit_count(world["plan_x"].pk)
    r = owner.post(f"/api/payments/{pay_id}/reject/", {}, format="json")
    assert r.status_code == 400
    assert "reason" in r.json()["error"]["fields"]
    assert _audit_count(world["plan_x"].pk) == before


@pytest.mark.django_db
def test_reject_reason_visible_in_member_open_dues(world):
    due = world["due_x"]
    _open(due)
    reason = "Wrong sender number"
    owner = client_for(world["owner"])
    pay_id = _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk], transaction_id="REJOPN01").json()["payment_id"]
    owner.post(f"/api/payments/{pay_id}/reject/", {"reason": reason}, format="json")
    due.refresh_from_db()
    assert due.status == DueStatus.DUE
    detail = client_for(world["member"]).get(f"/api/me/shared-plans/{world['plan_x'].pk}/").json()
    open_ids = {x["due_id"] for x in detail["open_dues"]}
    assert due.pk in open_ids
    assert due.rejection_reason == reason


@pytest.mark.django_db
def test_reverse_confirmed_payment(world):
    due = world["due_x"]
    _open(due)
    owner = client_for(world["owner"])
    pay_id = _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk], transaction_id="REVRSE01").json()["payment_id"]
    owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    before = _audit_count(world["plan_x"].pk)
    r = owner.post(f"/api/payments/{pay_id}/reverse/", {}, format="json")
    assert r.status_code == 200
    due.refresh_from_db()
    assert due.status == DueStatus.DUE
    assert Payment.objects.get(pk=pay_id).review_status == ReviewStatus.REVERSED
    assert _audit_count(world["plan_x"].pk) == before + 1


@pytest.mark.django_db
def test_reverse_only_confirmed(world):
    due = world["due_x"]
    _open(due)
    pay_id = _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk], transaction_id="REVPND01").json()["payment_id"]
    r = client_for(world["owner"]).post(f"/api/payments/{pay_id}/reverse/", {}, format="json")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "only_confirmed"


@pytest.mark.django_db
def test_reverse_cannot_reverse_when_newer_payment(world):
    due = world["due_x"]
    _open(due)
    owner = client_for(world["owner"])
    pay_id = _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk], transaction_id="REVBK01").json()["payment_id"]
    owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    shared = world["shared_x"]
    later = Payment.objects.create(
        shared_plan=shared,
        member=world["member_row"],
        recorded_by=world["owner"],
        method=PaymentMethod.CASH,
        transaction_id=None,
        amount=due.amount_bdt,
        paid_on=world["today"],
        review_status=ReviewStatus.CONFIRMED,
        reviewed_at=timezone.now(),
    )
    PaymentAllocation.objects.create(payment=later, due=due, amount_applied=due.amount_bdt)
    r = owner.post(f"/api/payments/{pay_id}/reverse/", {}, format="json")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "cannot_reverse"


@pytest.mark.django_db
def test_mark_paid_on_due(world):
    due = world["due_x"]
    _open(due)
    owner = client_for(world["owner"])
    today = world["today"]
    before = _audit_count(world["plan_x"].pk)
    r = owner.post(
        f"/api/dues/{due.pk}/mark-paid/",
        {"date": str(today), "method": PaymentMethod.CASH, "note": "cash"},
        format="json",
    )
    assert r.status_code == 200
    due.refresh_from_db()
    assert due.status == DueStatus.PAID
    assert _audit_count(world["plan_x"].pk) == before + 1


@pytest.mark.django_db
def test_mark_paid_rejects_pending_payment(world):
    due = world["due_x"]
    _open(due)
    pay_id = _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk], transaction_id="MKPND01").json()["payment_id"]
    owner = client_for(world["owner"])
    owner.post(
        f"/api/dues/{due.pk}/mark-paid/",
        {"date": str(world["today"]), "method": PaymentMethod.CASH, "note": "x"},
        format="json",
    )
    assert Payment.objects.get(pk=pay_id).review_status == ReviewStatus.REJECTED


@pytest.mark.django_db
def test_mark_paid_future_date(world):
    due = world["due_x"]
    _open(due)
    future = (world["today"] + timedelta(days=2)).isoformat()
    r = client_for(world["owner"]).post(
        f"/api/dues/{due.pk}/mark-paid/",
        {"date": future, "method": PaymentMethod.CASH, "note": "x"},
        format="json",
    )
    assert r.status_code == 400
    assert "date" in r.json()["error"]["fields"]


@pytest.mark.django_db
def test_mark_paid_already_paid(world):
    due = world["due_x"]
    due.status = DueStatus.PAID
    due.save(update_fields=["status"])
    r = client_for(world["owner"]).post(
        f"/api/dues/{due.pk}/mark-paid/",
        {"date": str(world["today"]), "method": PaymentMethod.CASH, "note": "x"},
        format="json",
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "already_paid"


@pytest.mark.django_db
def test_mark_paid_owner_seat_no_member_notification(world):
    shared = world["shared_x"]
    owner_member = Member.objects.get(shared_plan=shared, user=world["owner"])
    due = Due.objects.filter(charge=world["charge_x"], member=owner_member).first()
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    client_for(world["owner"]).post(
        f"/api/dues/{due.pk}/mark-paid/",
        {"date": str(world["today"]), "method": PaymentMethod.CASH, "note": ""},
        format="json",
    )
    assert not Notification.objects.filter(user=world["owner"], kind="payment_recorded").exists()


@pytest.mark.django_db
def test_waive_due(world):
    due = world["due_x"]
    _open(due)
    before = _audit_count(world["plan_x"].pk)
    r = client_for(world["owner"]).post(f"/api/dues/{due.pk}/waive/", {"note": "gift"}, format="json")
    assert r.status_code == 200
    assert Due.objects.get(pk=due.pk).status == DueStatus.WAIVED
    assert _audit_count(world["plan_x"].pk) == before + 1


@pytest.mark.django_db
def test_waive_pending_multi_due_payment_frees_other(world_rich):
    world = world_rich
    d1, d2 = _two_member_dues(world)
    pay_id = _submit(
        client_for(world["member"]), world["plan_x"].pk, [d1.pk, d2.pk], transaction_id="WAIVMU01"
    ).json()["payment_id"]
    owner = client_for(world["owner"])
    owner.post(f"/api/dues/{d1.pk}/waive/", {"note": "one month free"}, format="json")
    d2.refresh_from_db()
    assert d2.status == DueStatus.DUE
    assert "waived another due" in (d2.rejection_reason or "").lower()
    assert Payment.objects.get(pk=pay_id).review_status == ReviewStatus.REJECTED


@pytest.mark.django_db
def test_set_due_single_confirmed_reverses_payment(world):
    due = world["due_x"]
    _open(due)
    owner = client_for(world["owner"])
    pay_id = _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk], transaction_id="SETDUE01").json()["payment_id"]
    owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    owner.post(f"/api/dues/{due.pk}/set-due/", {}, format="json")
    assert Payment.objects.get(pk=pay_id).review_status == ReviewStatus.REVERSED
    assert Due.objects.get(pk=due.pk).status == DueStatus.DUE


@pytest.mark.django_db
def test_set_due_multi_due_use_reverse(world_rich):
    world = world_rich
    d1, d2 = _two_member_dues(world)
    pay_id = _submit(
        client_for(world["member"]), world["plan_x"].pk, [d1.pk, d2.pk], transaction_id="SETMUL01"
    ).json()["payment_id"]
    owner = client_for(world["owner"])
    owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    r = owner.post(f"/api/dues/{d1.pk}/set-due/", {}, format="json")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "use_reverse"


@pytest.mark.django_db
def test_set_due_owner_seat(world):
    shared = world["shared_x"]
    owner_member = Member.objects.get(shared_plan=shared, user=world["owner"])
    due = Due.objects.filter(charge=world["charge_x"], member=owner_member).first()
    due.status = DueStatus.PAID
    due.save(update_fields=["status"])
    owner = client_for(world["owner"])
    owner.post(f"/api/dues/{due.pk}/set-due/", {}, format="json")
    assert Due.objects.get(pk=due.pk).status == DueStatus.DUE


@pytest.mark.django_db
def test_set_due_waived(world):
    due = world["due_x"]
    due.status = DueStatus.WAIVED
    due.save(update_fields=["status"])
    client_for(world["owner"]).post(f"/api/dues/{due.pk}/set-due/", {}, format="json")
    assert Due.objects.get(pk=due.pk).status == DueStatus.DUE


@pytest.mark.django_db
def test_set_due_pending_409(world):
    due = world["due_x"]
    _open(due)
    _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk], transaction_id="SETPND01")
    r = client_for(world["owner"]).post(f"/api/dues/{due.pk}/set-due/", {}, format="json")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "already_decided"


@pytest.mark.django_db
def test_confirm_iou_then_reverse(world):
    shared = world["shared_x"]
    charge = world["charge_x"]
    owner_member = Member.objects.get(shared_plan=shared, user=world["owner"])
    owner_due = Due.objects.get(charge=charge, member=owner_member)
    owner_due.status = DueStatus.DUE
    owner_due.save(update_fields=["status"])
    owner = client_for(world["owner"])
    pay_id = _submit(
        client_for(world["member"]), world["plan_x"].pk, [owner_due.pk], transaction_id="IOUCHK01"
    ).json()["payment_id"]
    owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    ious = owner.get(f"/api/shared-plans/{world['plan_x'].pk}/ious/").json()
    assert len(ious) == 1
    owner.post(f"/api/payments/{pay_id}/reverse/", {}, format="json")
    assert owner.get(f"/api/shared-plans/{world['plan_x'].pk}/ious/").json() == []


@pytest.mark.django_db
def test_illegal_confirm_rejected_request_no_audit(world):
    due = world["due_x"]
    _open(due)
    owner = client_for(world["owner"])
    pay_id = _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk], transaction_id="NOAUDC1").json()["payment_id"]
    owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    before = _audit_count(world["plan_x"].pk)
    owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    assert _audit_count(world["plan_x"].pk) == before
