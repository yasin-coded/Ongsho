import pytest
from rest_framework.test import APIClient

from dues.models import DueStatus
from tests.test_subscriptions import assert_error_shape, client_for


@pytest.mark.django_db
def test_dues_list_anonymous_401():
    assert APIClient().get("/api/dues/").status_code == 401


@pytest.mark.django_db
def test_dues_list_owner_scoping(world):
    owner = client_for(world["owner"])
    member = client_for(world["member"])
    outsider = client_for(world["outsider"])
    assert owner.get("/api/dues/").status_code == 200
    assert outsider.get("/api/dues/").status_code == 200
    assert outsider.get("/api/dues/").json()["results"] == []
    member_rows = member.get("/api/dues/").json().get("results", [])
    for row in member_rows:
        assert row["plan"]["id"] == world["plan_y"].pk


@pytest.mark.django_db
def test_dues_list_invalid_filters(world):
    r = client_for(world["owner"]).get("/api/dues/?status=nope")
    assert r.status_code == 400
    assert_error_shape(r)
    r2 = client_for(world["owner"]).get("/api/dues/?month=not-a-month")
    assert r2.status_code == 400


@pytest.mark.django_db
def test_dues_list_shape(world):
    body = client_for(world["owner"]).get("/api/dues/").json()
    assert "results" in body
    if body["results"]:
        row = body["results"][0]
        assert "charge_id" in row and "is_owner_seat" in row
        assert set(row["plan"]) == {"id", "plan_name"}


@pytest.mark.django_db
def test_member_balance_owner_only(world):
    member = world["due_x"].member
    assert client_for(world["owner"]).get(f"/api/members/{member.pk}/balance/").status_code == 200
    assert client_for(world["member"]).get(f"/api/members/{member.pk}/balance/").status_code == 404


@pytest.mark.django_db
def test_members_list_has_due_fields(world):
    plan_id = world["plan_x"].pk
    body = client_for(world["owner"]).get(f"/api/shared-plans/{plan_id}/members/").json()
    assert body
    assert "due_status" in body[0]
