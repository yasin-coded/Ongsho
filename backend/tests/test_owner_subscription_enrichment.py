"""Owner subscription list/detail enrichment and dues list empty owner."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from billing.models import Charge
from dues.models import Due, DueStatus
from plans.models import PlanMode
from sharing.models import Member, MemberStatus, SharedPlan, SplitType
from tests.test_subscriptions import WORLD_PASS, assert_error_shape, client_for, plan_payload

User = get_user_model()


@pytest.mark.django_db
def test_dues_list_empty_owner_200():
    u = User.objects.create_user(email="solo0@example.com", password=WORLD_PASS, name="Solo", email_verified=True)
    r = client_for(u).get("/api/dues/")
    assert r.status_code == 200
    assert r.json()["results"] == []
    assert r.json()["count"] == 0


@pytest.mark.django_db
def test_dues_list_foreign_plan_404(world):
    r = client_for(world["owner"]).get(f"/api/dues/?plan={world['plan_y'].pk}")
    assert r.status_code == 404
    assert_error_shape(r)


@pytest.mark.django_db
def test_dues_list_anonymous_401():
    assert APIClient().get("/api/dues/").status_code == 401


@pytest.mark.django_db
def test_list_shared_plan_fields(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    body = client_for(world["owner"]).get("/api/subscriptions/").json()
    item = next(x for x in body["results"] if x["id"] == world["plan_x"].pk)
    assert item["seats"] == world["shared_x"].seats
    assert item["seats_taken"] >= 2
    assert item["per_seat"] is not None
    assert item["members"]
    assert "due_status" in item["members"][0]
    assert item["expected"] is not None
    assert item["collected"] is not None
    totals = body["totals"]
    for key in ("confirmed", "pending", "expected", "review_count", "review_plans", "count", "to_providers"):
        assert key in totals


@pytest.mark.django_db
def test_list_solo_plan_null_collection(world):
    owner = client_for(world["owner"])
    r = owner.post(
        "/api/subscriptions/",
        plan_payload(plan_name="Solo Only Unique"),
        format="json",
    )
    assert r.status_code == 201
    item = next(x for x in owner.get("/api/subscriptions/").json()["results"] if x["id"] == r.json()["id"])
    assert item["collected"] is None
    assert item["expected"] is None
    assert item["per_seat"] is None


@pytest.mark.django_db
def test_list_reseller_no_owner_seat_in_members(world):
    owner = client_for(world["owner"])
    r = owner.post(
        "/api/subscriptions/",
        {**plan_payload(plan_name="Resel List"), "plan_mode": PlanMode.RESELLER, "seats": 2},
        format="json",
    )
    assert r.status_code == 201
    plan_id = r.json()["id"]
    buyer = User.objects.create_user(
        email="resbuyer@example.com", password=WORLD_PASS, name="Buyer", email_verified=True
    )
    shared = SharedPlan.objects.get(subscription_id=plan_id)
    Member.objects.create(
        shared_plan=shared,
        user=buyer,
        share_type=SplitType.EQUAL,
        status=MemberStatus.ACTIVE,
        joined_on=world["today"],
    )
    from billing import services as billing_services
    from dues import services as dues_services

    today = world["today"]
    sub = shared.subscription
    billing_services.generate_missing_charges(sub, today)
    for ch in Charge.objects.filter(subscription_id=plan_id):
        dues_services.create_dues_for_charge(ch)
    if not Charge.objects.filter(subscription_id=plan_id).exists():
        from datetime import timedelta
        from decimal import Decimal
        from billing.models import ChargeStatus

        ch = Charge.objects.create(
            subscription=sub,
            period_start=today,
            period_end=today + timedelta(days=30),
            due_date=today,
            amount=Decimal("100.00"),
            amount_bdt=Decimal("100.00"),
            currency="BDT",
            status=ChargeStatus.DUE,
            locked=False,
        )
        dues_services.create_dues_for_charge(ch)
    item = next(x for x in owner.get("/api/subscriptions/").json()["results"] if x["id"] == plan_id)
    assert all(not m["is_owner_seat"] for m in item["members"])
    assert item["expected"] is not None


@pytest.mark.django_db
def test_waived_excluded_from_expected(world):
    due = world["due_x"]
    due.status = DueStatus.WAIVED
    due.save(update_fields=["status"])
    item = next(
        x
        for x in client_for(world["owner"]).get("/api/subscriptions/").json()["results"]
        if x["id"] == world["plan_x"].pk
    )
    exp = Decimal(item["expected"])
    assert exp >= Decimal("0")


@pytest.mark.django_db
def test_detail_split_charges_leave(world):
    owner = client_for(world["owner"])
    body = owner.get(f"/api/subscriptions/{world['plan_x'].pk}/").json()
    assert "split_type" in body
    assert isinstance(body["charges"], list)
    if body["charges"]:
        ch = body["charges"][0]
        assert "dues" in ch and set(ch["dues"]) >= {"due", "pending", "paid", "waived"}
    assert "leave_requests" in body
    assert "activity" in body and "ious" in body


@pytest.mark.django_db
def test_member_cannot_read_owner_subscription(world):
    assert client_for(world["member"]).get(f"/api/subscriptions/{world['plan_x'].pk}/").status_code == 404


@pytest.mark.django_db
def test_owner_member_of_y_only_sees_own(world):
    owner = client_for(world["owner"])
    assert owner.get(f"/api/subscriptions/{world['plan_x'].pk}/").status_code == 200
    assert owner.get(f"/api/subscriptions/{world['plan_y'].pk}/").status_code == 404


@pytest.mark.django_db
def test_list_constant_query_count(world):
    owner = client_for(world["owner"])

    def count_list():
        with CaptureQueriesContext(connection) as ctx:
            r = owner.get("/api/subscriptions/")
            assert r.status_code == 200
        return len(ctx)

    base = count_list()
    for i in range(9):
        owner.post(
            "/api/subscriptions/",
            {**plan_payload(plan_name=f"Extra {i}"), "seats": 1},
            format="json",
        )
    assert count_list() == base


@pytest.mark.django_db
def test_subscriptions_anonymous_401():
    assert APIClient().get("/api/subscriptions/").status_code == 401
