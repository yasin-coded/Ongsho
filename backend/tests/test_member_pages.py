import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from payments.models import Payment, PaymentAllocation, ReviewStatus
from rest_framework.test import APIClient

from core.choices import PaymentMethod
from tests.test_subscriptions import client_for


@pytest.mark.django_db
def test_me_shared_plans_anonymous_401():
    assert APIClient().get("/api/me/shared-plans/").status_code == 401


@pytest.mark.django_db
def test_me_shared_plans_member_not_owner(world):
    r = client_for(world["member"]).get("/api/me/shared-plans/")
    assert r.status_code == 200
    body = r.json()
    assert "counts" in body and "totals" in body
    ids = {p["plan_id"] for p in body["results"]}
    assert world["plan_x"].pk in ids
    assert world["plan_y"].pk not in ids


@pytest.mark.django_db
def test_me_shared_plan_detail_404_for_owner_route(world):
    assert client_for(world["owner"]).get(f"/api/me/shared-plans/{world['plan_x'].pk}/").status_code == 404
    assert client_for(world["member"]).get(f"/api/me/shared-plans/{world['plan_x'].pk}/").status_code == 200


@pytest.mark.django_db
def test_member_detail_no_foreign_emails_in_members_list(world):
    data = client_for(world["member"]).get(f"/api/me/shared-plans/{world['plan_x'].pk}/").json()
    for m in data["members"]:
        assert "email" not in m
        assert "due_status" not in m
        assert "status" not in m


@pytest.mark.django_db
def test_coverable_excludes_own_dues(world):
    data = client_for(world["member"]).get(f"/api/me/shared-plans/{world['plan_x'].pk}/").json()
    mine = world["shared_x"].members.get(user=world["member"]).pk
    for row in data["coverable"]:
        assert row["due_id"] != world["due_x"].pk


@pytest.mark.django_db
def test_owner_sees_member_email_on_members_endpoint(world):
    owner_rows = client_for(world["owner"]).get(
        f"/api/shared-plans/{world['plan_x'].pk}/members/"
    ).json()
    assert "email" in owner_rows[0]


@pytest.mark.django_db
def test_me_shared_plans_query_count_stable(world):
    member = world["member"]
    client = client_for(member)
    with CaptureQueriesContext(connection) as ctx:
        client.get("/api/me/shared-plans/")
    first = len(ctx)
    with CaptureQueriesContext(connection) as ctx2:
        client.get("/api/me/shared-plans/")
    assert len(ctx2) == first
