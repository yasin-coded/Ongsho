import pytest
from django.contrib.auth import get_user_model

from core.dates import today_dhaka
from notifications.models import Notification
from sharing.models import Member, MemberStatus

from tests.test_subscriptions import WORLD_PASS, client_for, plan_payload

User = get_user_model()


@pytest.mark.django_db
def test_leave_request_owner_seat_refused(world):
    owner_seat = world["shared_x"].members.get(user=world["owner"])
    r = client_for(world["owner"]).post(
        f"/api/shared-plans/{world['plan_x'].pk}/leave-request/",
        {},
        format="json",
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "owner_cannot_leave"


@pytest.mark.django_db
def test_member_leave_request(world):
    r = client_for(world["member"]).post(
        f"/api/shared-plans/{world['plan_x'].pk}/leave-request/",
        {},
        format="json",
    )
    assert r.status_code == 200
    world["shared_x"].members.get(user=world["member"]).refresh_from_db()
    assert world["shared_x"].members.get(user=world["member"]).status == MemberStatus.LEAVE_REQUESTED


@pytest.mark.django_db
def test_removed_member_does_not_get_plan_deleted_notification(world):
    """After removal, ex-members should only have leave_result — not plan_deleted."""
    owner_client = client_for(world["owner"])
    member_row = world["shared_x"].members.get(user=world["member"])
    today = today_dhaka()
    remove = owner_client.post(
        f"/api/members/{member_row.pk}/leave/",
        {"approve": True, "leave_date": today.isoformat(), "unpaid": "keep"},
        format="json",
    )
    assert remove.status_code == 200, remove.content
    member_row.refresh_from_db()
    assert member_row.status == MemberStatus.LEFT

    before = Notification.objects.filter(user=world["member"], kind="plan_deleted").count()
    delete = owner_client.delete(
        f"/api/subscriptions/{world['plan_x'].pk}/",
        {"password": WORLD_PASS},
        format="json",
    )
    assert delete.status_code == 204, delete.content
    after = Notification.objects.filter(user=world["member"], kind="plan_deleted").count()
    assert after == before
    assert Notification.objects.filter(user=world["member"], kind="leave_result").exists()
