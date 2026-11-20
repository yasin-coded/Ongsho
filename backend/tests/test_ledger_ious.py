from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework.test import APIClient

from billing.models import Charge
from billing import services as billing_services
from core.choices import PaymentMethod
from dues.models import Due, DueStatus
from dues import services as dues_services
from payments.models import Payment, PaymentAllocation, ReviewStatus
from plans.models import PlanMode, Subscription
from sharing.models import Member, MemberStatus, SharedPlan, SplitType
from tests.test_payment_decisions import _submit
from tests.test_subscriptions import assert_error_shape, client_for, plan_payload

User = get_user_model()

OWNER_ROUTES = ("ledger", "ious", "review")


def _ledger(owner_client, plan_id, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    url = f"/api/shared-plans/{plan_id}/ledger/"
    if q:
        url += f"?{q}"
    return owner_client.get(url)


@pytest.mark.django_db
def test_ledger_anonymous_401(world):
    assert APIClient().get(f"/api/shared-plans/{world['plan_x'].pk}/ledger/").status_code == 401


@pytest.mark.django_db
def test_ledger_member_and_outsider_404(world):
    pid = world["plan_x"].pk
    assert client_for(world["member"]).get(f"/api/shared-plans/{pid}/ledger/").status_code == 404
    assert client_for(world["outsider"]).get(f"/api/shared-plans/{pid}/ledger/").status_code == 404


@pytest.mark.django_db
def test_owner_on_other_plan_404(world):
    """Owner of X who is only a member on Y cannot open Y's ledger."""
    assert client_for(world["owner"]).get(f"/api/shared-plans/{world['plan_y'].pk}/ledger/").status_code == 404


@pytest.mark.django_db
def test_ledger_filters_totals_months_people(world):
    owner = client_for(world["owner"])
    plan = world["plan_x"]
    r = _ledger(owner, plan.pk)
    assert r.status_code == 200
    body = r.json()
    assert "totals" in body
    assert set(body["totals"]) == {"paid", "pending", "due", "waived", "all"}
    assert "months" in body and len(body["months"]) >= 1
    assert "people" in body and len(body["people"]) >= 2
    assert "results" in body
    row = body["results"][0]
    for key in (
        "due_id",
        "charge_id",
        "month",
        "due_date",
        "member",
        "amount",
        "status",
        "recorded_by_owner",
        "covered_by",
        "payment_id",
    ):
        assert key in row

    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    pay_id = _submit(client_for(world["member"]), plan.pk, due.pk, tid="LEDGER01").json()["payment_id"]
    r2 = _ledger(owner, plan.pk, status="pending")
    assert r2.status_code == 200
    assert all(x["status"] == "pending" for x in r2.json()["results"])
    assert Decimal(r2.json()["totals"]["pending"]) > 0

    owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    r3 = _ledger(owner, plan.pk, member=due.member_id, month=world["charge_x"].period_start.strftime("%Y-%m"))
    assert r3.status_code == 200
    assert r3.json()["totals"]["paid"] == r3.json()["totals"]["all"]


@pytest.mark.django_db
def test_ledger_invalid_filters_400(world):
    owner = client_for(world["owner"])
    pid = world["plan_x"].pk
    for url in (
        f"/api/shared-plans/{pid}/ledger/?month=bad",
        f"/api/shared-plans/{pid}/ledger/?status=nope",
        f"/api/shared-plans/{pid}/ledger/?member=999999",
    ):
        r = owner.get(url)
        assert r.status_code == 400
        assert_error_shape(r)


@pytest.mark.django_db
def test_ledger_pagination(world):
    owner = client_for(world["owner"])
    pid = world["plan_x"].pk
    r = owner.get(f"/api/shared-plans/{pid}/ledger/?page=1&page_size=2")
    assert r.status_code == 200
    body = r.json()
    assert len(body["results"]) <= 2
    assert body["count"] >= len(body["results"])


@pytest.mark.django_db
def test_ledger_covered_by_and_recorded_by_owner(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    owner = client_for(world["owner"])
    today = world["today"]
    owner.post(
        f"/api/dues/{due.pk}/mark-paid/",
        {"date": str(today), "method": PaymentMethod.CASH, "note": "x"},
        format="json",
    )
    r = _ledger(owner, world["plan_x"].pk, status="paid")
    row = next(x for x in r.json()["results"] if x["due_id"] == due.pk)
    assert row["recorded_by_owner"] is True
    assert row["paid_on"] == str(today)


@pytest.mark.django_db
def test_ledger_constant_query_count(world):
    owner = client_for(world["owner"])
    plan = world["shared_x"]
    pid = world["plan_x"].pk

    def count_queries():
        with CaptureQueriesContext(connection) as ctx:
            r = _ledger(owner, pid)
            assert r.status_code == 200
        return len(ctx)

    base = count_queries()
    for i in range(8):
        u = User.objects.create_user(
            email=f"extra{i}@example.com",
            password="pass12345",
            name=f"Extra {i}",
            email_verified=True,
        )
        Member.objects.create(
            shared_plan=plan,
            user=u,
            share_type=SplitType.EQUAL,
            status=MemberStatus.ACTIVE,
            joined_on=world["plan_x"].start_date,
        )
    after = count_queries()
    assert after == base


@pytest.mark.django_db
def test_ious_netting_pair(world_rich):
    world = world_rich
    plan = world["plan_x"]
    shared = world["shared_x"]
    charge = world["charge_x"]
    member_a = world["member_row"]
    member_b = world["member_rows"][1]
    due_a = Due.objects.get(charge=charge, member=member_a)
    due_b = Due.objects.get(charge=charge, member=member_b)
    due_a.status = DueStatus.DUE
    due_b.status = DueStatus.DUE
    due_a.save(update_fields=["status"])
    due_b.save(update_fields=["status"])

    owner_client = client_for(world["owner"])
    client_a = client_for(world["member"])
    client_b = client_for(world["member_b"])

    pay1 = client_a.post(
        "/api/payments/",
        {
            "plan_id": plan.pk,
            "due_ids": [due_b.pk],
            "method": PaymentMethod.BKASH,
            "transaction_id": "IOUNET01",
        },
        format="json",
    ).json()["payment_id"]
    owner_client.post(f"/api/payments/{pay1}/confirm/", {}, format="json")

    pay2 = client_b.post(
        "/api/payments/",
        {
            "plan_id": plan.pk,
            "due_ids": [due_a.pk],
            "method": PaymentMethod.BKASH,
            "transaction_id": "IOUNET02",
        },
        format="json",
    ).json()["payment_id"]
    owner_client.post(f"/api/payments/{pay2}/confirm/", {}, format="json")

    items = owner_client.get(f"/api/shared-plans/{plan.pk}/ious/").json()
    if due_a.amount_bdt == due_b.amount_bdt:
        assert items == []
    else:
        assert len(items) == 1


@pytest.mark.django_db
def test_ious_excludes_non_confirmed(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    owner = client_for(world["owner"])
    member = client_for(world["member"])
    pid = world["plan_x"].pk
    pay_id = _submit(member, pid, due.pk, tid="IOUREJ01").json()["payment_id"]
    assert owner.get(f"/api/shared-plans/{pid}/ious/").json() == []
    owner.post(f"/api/payments/{pay_id}/reject/", {"reason": "no"}, format="json")
    assert owner.get(f"/api/shared-plans/{pid}/ious/").json() == []


@pytest.mark.django_db
def test_ious_three_person_net(world):
    """Build IOUs with manual confirmed allocations when needed."""
    shared = world["shared_x"]
    charge = world["charge_x"]
    members = list(Member.objects.filter(shared_plan=shared).select_related("user"))
    if len(members) < 2:
        pytest.skip("not enough members")
    m0, m1 = members[0], members[1]
    d0 = Due.objects.get(charge=charge, member=m0)
    d1 = Due.objects.get(charge=charge, member=m1)
    for d in (d0, d1):
        d.status = DueStatus.PAID
        d.save(update_fields=["status"])
    pay_a = Payment.objects.create(
        shared_plan=shared,
        member=m0,
        recorded_by=m0.user,
        method=PaymentMethod.BKASH,
        transaction_id="THREEP01",
        amount=d1.amount_bdt,
        review_status=ReviewStatus.CONFIRMED,
    )
    PaymentAllocation.objects.create(payment=pay_a, due=d1, amount_applied=d1.amount_bdt)
    pay_b = Payment.objects.create(
        shared_plan=shared,
        member=m1,
        recorded_by=m1.user,
        method=PaymentMethod.BKASH,
        transaction_id="THREEP02",
        amount=Decimal("100.00"),
        review_status=ReviewStatus.CONFIRMED,
    )
    PaymentAllocation.objects.create(payment=pay_b, due=d0, amount_applied=Decimal("100.00"))
    r = client_for(world["owner"]).get(f"/api/shared-plans/{world['plan_x'].pk}/ious/")
    assert r.status_code == 200
    assert len(r.json()) >= 1


@pytest.mark.django_db
def test_reseller_ious_empty(db):
    owner = User.objects.create_user(
        email="resel@example.com", password="pass12345", name="Resel", email_verified=True
    )
    client = client_for(owner)
    r = client.post(
        "/api/subscriptions/",
        {**plan_payload(plan_name="Reseller"), "plan_mode": PlanMode.RESELLER, "seats": 2},
        format="json",
    )
    assert r.status_code == 201
    pid = r.json()["id"]
    assert client.get(f"/api/shared-plans/{pid}/ious/").json() == []


@pytest.mark.django_db
def test_member_ious_scoped(world):
    shared = world["shared_x"]
    charge = world["charge_x"]
    m0 = world["member_row"]
    m1 = Member.objects.get(shared_plan=shared, user=world["owner"])
    d1 = Due.objects.get(charge=charge, member=m1)
    d1.status = DueStatus.PAID
    d1.save(update_fields=["status"])
    pay = Payment.objects.create(
        shared_plan=shared,
        member=m0,
        recorded_by=m0.user,
        method=PaymentMethod.BKASH,
        transaction_id="MEMIOU01",
        amount=d1.amount_bdt,
        review_status=ReviewStatus.CONFIRMED,
    )
    PaymentAllocation.objects.create(payment=pay, due=d1, amount_applied=d1.amount_bdt)
    outsider = User.objects.create_user(
        email="third@example.com", password="pass12345", name="Third", email_verified=True
    )
    third_member = Member.objects.create(
        shared_plan=shared,
        user=outsider,
        share_type=SplitType.EQUAL,
        status=MemberStatus.ACTIVE,
        joined_on=world["plan_x"].start_date,
    )
    from dues import services as dues_services

    dues_services.create_dues_for_charge(charge)
    owner_member = m1
    d_third = Due.objects.get(charge=charge, member=third_member)
    pay2 = Payment.objects.create(
        shared_plan=shared,
        member=owner_member,
        recorded_by=world["owner"],
        method=PaymentMethod.BKASH,
        transaction_id="MEMIOU02",
        amount=d_third.amount_bdt,
        review_status=ReviewStatus.CONFIRMED,
    )
    PaymentAllocation.objects.create(payment=pay2, due=d_third, amount_applied=d_third.amount_bdt)
    r = client_for(world["member"]).get(f"/api/me/shared-plans/{world['plan_x'].pk}/")
    assert r.status_code == 200
    ious = r.json()["ious"]
    assert len(ious) == 1
    assert ious[0]["you_owe"] is False
    third_ious = client_for(outsider).get(f"/api/me/shared-plans/{world['plan_x'].pk}/").json()["ious"]
    assert len(third_ious) == 1 and third_ious[0]["you_owe"] is True


@pytest.mark.django_db
def test_member_cannot_hit_owner_routes(world):
    pid = world["plan_x"].pk
    client = client_for(world["member"])
    for route in OWNER_ROUTES:
        assert client.get(f"/api/shared-plans/{pid}/{route}/").status_code == 404


@pytest.mark.django_db
def test_subscription_detail_has_ious_and_activity(world):
    from audit.models import AuditLog

    AuditLog.objects.create(
        user=world["owner"],
        action="payment.submitted",
        entity_type="Payment",
        entity_id=1,
        plan_id=world["plan_x"].pk,
        summary="Member sent 500.00 BDT (ID TEST01)",
        amount=Decimal("500.00"),
    )
    r = client_for(world["owner"]).get(f"/api/subscriptions/{world['plan_x'].pk}/")
    assert r.status_code == 200
    body = r.json()
    assert "activity" in body
    assert any(a["text"] == "Member sent 500.00 BDT (ID TEST01)" and a["tone"] == "pending" for a in body["activity"])
    assert "ious" in body
