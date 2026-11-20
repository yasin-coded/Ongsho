import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from sharing import services
from sharing.models import Member, SharedPlan
from tests.test_subscriptions import WORLD_PASS, client_for, plan_payload

User = get_user_model()

pytestmark = pytest.mark.django_db


def _share_plan(owner_client):
    r = owner_client.post(
        "/api/subscriptions/",
        {**plan_payload(), "seats": 3},
        format="json",
    )
    assert r.status_code == 201, r.content
    plan_id = r.json()["id"]
    shared = SharedPlan.objects.get(subscription_id=plan_id)
    token = services.make_plan_join_token(shared)
    return plan_id, token, owner_client


def test_owner_gets_join_link_when_seats_free(db):
    owner = User.objects.create_user(
        email="owner-join@example.com", password=WORLD_PASS, name="Owner", email_verified=True
    )
    plan_id, token, owner_client = _share_plan(client_for(owner))
    meta = owner_client.get(f"/api/shared-plans/{plan_id}/").json()
    assert meta["join_link_available"] is True
    assert "/join/" in meta["join_link"]
    public = APIClient().get(f"/api/join/{token}/").json()
    assert public["can_join"] is True
    assert public["kind"] == "plan"


def test_plan_full_blocks_join(db):
    owner = User.objects.create_user(
        email="full-owner@example.com", password=WORLD_PASS, name="Owner", email_verified=True
    )
    plan_id, token, owner_client = _share_plan(client_for(owner))
    for i in range(2):
        guest = User.objects.create_user(
            email=f"guest{i}@example.com",
            password=WORLD_PASS,
            name=f"G{i}",
            email_verified=True,
        )
        r = client_for(guest).post(f"/api/join/{token}/accept/", format="json")
        assert r.status_code == 200, r.content
    meta = owner_client.get(f"/api/shared-plans/{plan_id}/").json()
    assert meta["join_link_available"] is False
    newbie = User.objects.create_user(
        email="late@example.com", password=WORLD_PASS, name="Late", email_verified=True
    )
    blocked = client_for(newbie).post(f"/api/join/{token}/accept/", format="json")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "plan_full"


def test_signup_and_join_via_plan_link(db):
    owner = User.objects.create_user(
        email="owner-sj@example.com", password=WORLD_PASS, name="Owner", email_verified=True
    )
    _, token, _ = _share_plan(client_for(owner))
    r = APIClient().post(
        f"/api/join/{token}/signup/",
        {
            "email": "brand-new@example.com",
            "name": "Brand New",
            "password": WORLD_PASS,
        },
        format="json",
    )
    assert r.status_code == 201, r.content
    user = User.objects.get(email="brand-new@example.com")
    assert Member.objects.filter(user=user).exists()