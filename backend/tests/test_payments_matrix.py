"""Submit-payment API matrix."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from notifications.models import Notification
from payments.models import Payment, ReviewStatus
from rest_framework.test import APIClient

from audit.models import AuditLog
from billing.models import Charge, ChargeStatus
from core.choices import PaymentMethod
from dues.models import Due, DueStatus
from plans.models import PlanMode
from sharing.models import Member, MemberStatus, SharedPlan, SplitType
from tests.helpers import run_concurrently
from tests.test_payments import _submit
from tests.test_subscriptions import assert_error_shape, client_for, plan_payload

User = get_user_model()


def _open(due):
    due.status = DueStatus.DUE
    due.rejection_reason = ""
    due.waiver_note = ""
    due.save(update_fields=["status", "rejection_reason", "waiver_note"])


def _audit_count(plan_id: int) -> int:
    return AuditLog.objects.filter(plan_id=plan_id).exclude(summary="").count()


@pytest.mark.django_db
def test_submit_not_member_404(world):
    _open(world["due_x"])
    r = _submit(client_for(world["outsider"]), world["plan_x"].pk, [world["due_x"].pk])
    assert r.status_code == 404


@pytest.mark.django_db
def test_submit_owner_403(world):
    _open(world["due_x"])
    r = _submit(client_for(world["owner"]), world["plan_x"].pk, [world["due_x"].pk])
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "owner_cannot_submit"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status",
    [DueStatus.PENDING, DueStatus.PAID, DueStatus.WAIVED],
)
def test_submit_due_not_open_unchanged(world, status):
    due = world["due_x"]
    due.status = status
    due.save(update_fields=["status"])
    before = _audit_count(world["plan_x"].pk)
    r = _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk], transaction_id="NOTOPEN1")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "due_not_open"
    due.refresh_from_db()
    assert due.status == status
    assert _audit_count(world["plan_x"].pk) == before


@pytest.mark.django_db
def test_reseller_cannot_pay_others_due(world_rich):
    world = world_rich
    plan_id = world["reseller_plan"].pk
    buyer = world["reseller_buyers"][0]
    buyer_due = world["reseller_buyer_due"]
    other = world["reseller_other_due"]
    _open(other)
    r = _submit(client_for(buyer), plan_id, [other.pk], transaction_id="RESEL001")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "reseller_own_dues_only"
    _open(buyer_due)
    assert _submit(client_for(buyer), plan_id, [buyer_due.pk], transaction_id="RESEL002").status_code == 201


@pytest.mark.django_db
def test_submit_covers_other_member_and_owner_seat(world):
    shared = world["shared_x"]
    charge = world["charge_x"]
    owner_member = Member.objects.get(shared_plan=shared, user=world["owner"])
    owner_due = Due.objects.get(charge=charge, member=owner_member)
    owner_due.status = DueStatus.DUE
    owner_due.save(update_fields=["status"])
    member_due = world["due_x"]
    _open(member_due)
    r = _submit(
        client_for(world["member"]),
        world["plan_x"].pk,
        [owner_due.pk],
        transaction_id="OWNSEAT1",
    )
    assert r.status_code == 201
    owner_due.refresh_from_db()
    assert owner_due.status == DueStatus.PENDING


@pytest.mark.django_db
def test_submit_amount_mismatch(world):
    due = world["due_x"]
    _open(due)
    r = _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk], amount="0.01", transaction_id="MISMCH01")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "amount_mismatch"
    due.refresh_from_db()
    assert due.status == DueStatus.DUE


@pytest.mark.django_db
def test_submit_future_paid_on(world):
    due = world["due_x"]
    _open(due)
    future = (world["today"] + timedelta(days=1)).isoformat()
    r = _submit(
        client_for(world["member"]),
        world["plan_x"].pk,
        [due.pk],
        paid_on=future,
        transaction_id="FUTURE01",
    )
    assert r.status_code == 400
    assert "paid_on" in r.json()["error"]["fields"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "tid,field",
    [
        ("AB", "transaction_id"),
        ("A" * 65, "transaction_id"),
        ("BAD!!", "transaction_id"),
        ("4111111111111111", "transaction_id"),
    ],
)
def test_submit_transaction_id_validation(world, tid, field):
    due = world["due_x"]
    _open(due)
    r = _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk], transaction_id=tid)
    assert r.status_code == 400
    assert field in r.json()["error"]["fields"]
    assert_error_shape(r)


@pytest.mark.django_db
def test_submit_tid_normalized_on_success(world):
    due = world["due_x"]
    _open(due)
    raw = "ab12 cd34ef"
    r = _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk], transaction_id=raw)
    assert r.status_code == 201
    pay = Payment.objects.get(pk=r.json()["payment_id"])
    assert pay.transaction_id == "AB12CD34EF"


@pytest.mark.django_db
def test_submit_duplicate_tid_case_and_spaces(world):
    due = world["due_x"]
    _open(due)
    member = client_for(world["member"])
    assert _submit(member, world["plan_x"].pk, [due.pk], transaction_id="dup sp01").status_code == 201
    due2 = Due.objects.filter(charge__subscription=world["plan_x"]).exclude(pk=due.pk).first()
    if due2 is None:
        due.status = DueStatus.DUE
        due.save(update_fields=["status"])
        due2 = due
    else:
        _open(due2)
    r = _submit(member, world["plan_x"].pk, [due2.pk], transaction_id="DUP SP01")
    assert r.status_code == 400
    assert "transaction_id" in r.json()["error"]["fields"]


@pytest.mark.django_db
def test_submit_duplicate_tid_after_rejected(world):
    due = world["due_x"]
    _open(due)
    member = client_for(world["member"])
    owner = client_for(world["owner"])
    tid = "REJTD001"
    pay_id = _submit(member, world["plan_x"].pk, [due.pk], transaction_id=tid).json()["payment_id"]
    owner.post(f"/api/payments/{pay_id}/reject/", {"reason": "no"}, format="json")
    _open(due)
    r = _submit(member, world["plan_x"].pk, [due.pk], transaction_id=tid)
    assert r.status_code == 400
    assert "transaction_id" in r.json()["error"]["fields"]


@pytest.mark.django_db
def test_submit_sets_pending_and_notifies_owner(world):
    due = world["due_x"]
    _open(due)
    before = _audit_count(world["plan_x"].pk)
    r = _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk], transaction_id="NOTIFY01")
    assert r.status_code == 201
    due.refresh_from_db()
    assert due.status == DueStatus.PENDING
    note = Notification.objects.filter(user=world["owner"], kind="payment_submitted").latest("id")
    assert note.payload["action"]["payment_id"] == r.json()["payment_id"]
    assert note.payload["action"]["plan_id"] == world["plan_x"].pk
    assert _audit_count(world["plan_x"].pk) == before + 1


@pytest.mark.django_db
def test_submit_rejected_request_no_audit(world):
    due = world["due_x"]
    due.status = DueStatus.PAID
    due.save(update_fields=["status"])
    before = _audit_count(world["plan_x"].pk)
    _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk], transaction_id="NOAUD001")
    assert _audit_count(world["plan_x"].pk) == before


@pytest.mark.django_db(transaction=True)
def test_concurrent_submit_same_due(world):
    due = world["due_x"]
    _open(due)
    member = world["member"]
    results, _ = run_concurrently(
        [
            lambda: _submit(client_for(member), world["plan_x"].pk, [due.pk], transaction_id="CONC1A01").status_code,
            lambda: _submit(client_for(member), world["plan_x"].pk, [due.pk], transaction_id="CONC1B02").status_code,
        ]
    )
    assert Payment.objects.filter(shared_plan=world["shared_x"], review_status=ReviewStatus.PENDING).count() == 1
    assert 201 in results
    assert 409 in results


@pytest.mark.django_db(transaction=True)
def test_concurrent_submit_same_transaction_id(world):
    due = world["due_x"]
    _open(due)
    member = world["member"]
    tid = "SAMETID1"
    results, _ = run_concurrently(
        [
            lambda: _submit(client_for(member), world["plan_x"].pk, [due.pk], transaction_id=tid).status_code,
            lambda: _submit(client_for(member), world["plan_x"].pk, [due.pk], transaction_id=tid).status_code,
        ]
    )
    assert Payment.objects.filter(shared_plan=world["shared_x"], transaction_id=tid).count() == 1
    assert 201 in results
    assert 400 in results or 409 in results


@pytest.mark.django_db
def test_submit_anonymous_401():
    assert APIClient().post("/api/payments/", {}, format="json").status_code == 401
