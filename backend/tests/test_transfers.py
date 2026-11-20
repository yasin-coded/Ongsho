from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from audit.models import AuditLog
from billing.models import Charge, ChargeStatus
from core.dates import today_dhaka
from dues.models import Due, DueStatus
from notifications.models import Notification
from payments.models import Payment, PaymentAllocation, ReviewStatus
from sharing.models import Member, MemberStatus, OwnershipTransfer, TransferStatus

from tests.test_subscriptions import assert_error_shape, client_for

PASS = "pass12345"


def ensure_owner_seat(world):
    shared = world["shared_x"]
    if not Member.objects.filter(shared_plan=shared, user=world["owner"]).exists():
        Member.objects.create(
            shared_plan=shared,
            user=world["owner"],
            share_type=shared.split_type,
            status=MemberStatus.ACTIVE,
            joined_on="2026-01-05",
        )
    return Member.objects.get(shared_plan=shared, user=world["member"])


def start_transfer(client, plan_id, member_id):
    return client.post(
        f"/api/shared-plans/{plan_id}/transfer/",
        {"member_id": member_id, "password": PASS},
        format="json",
    )


@pytest.mark.django_db
class TestOwnershipTransfer:
    def test_start_success(self, world):
        target = ensure_owner_seat(world)
        client = client_for(world["owner"])
        r = start_transfer(client, world["plan_x"].pk, target.pk)
        assert r.status_code == 201
        body = r.json()
        assert body["status"] == "pending"
        assert body["to"]["id"] == world["member"].pk
        assert OwnershipTransfer.objects.filter(status=TransferStatus.PENDING).count() == 1
        assert Notification.objects.filter(kind="transfer", user=world["member"]).exists()

    def test_non_owner_404(self, world):
        target = ensure_owner_seat(world)
        r = start_transfer(client_for(world["outsider"]), world["plan_x"].pk, target.pk)
        assert r.status_code == 404

    def test_reseller_400(self, world):
        from catalog.models import Category, ServiceName
        from core.choices import Currency, PaymentMethod
        from plans.models import CycleUnit, PlanMode, RenewalType, Subscription, SubscriptionStatus
        from sharing.models import SharedPlan, SplitType

        streaming = Category.objects.get(is_preset=True, name="Streaming")
        netflix = ServiceName.objects.get(is_preset=True, name="Netflix", category=streaming)
        sub = Subscription.objects.create(
            owner=world["owner"],
            service_name=netflix,
            category=streaming,
            plan_name="Reseller",
            plan_mode=PlanMode.RESELLER,
            currency=Currency.BDT,
            cycle_unit=CycleUnit.MONTH,
            cycle_count=1,
            anchor_day=1,
            start_date=today_dhaka(),
            renewal_type=RenewalType.AUTO,
            status=SubscriptionStatus.ACTIVE,
            recommended_method=PaymentMethod.BKASH,
            billing_from=today_dhaka(),
        )
        SharedPlan.objects.create(subscription=sub, split_type=SplitType.EQUAL, seats=2)
        member = Member.objects.create(
            shared_plan=sub.shared_plan,
            user=world["member"],
            share_type=SplitType.EQUAL,
            status=MemberStatus.ACTIVE,
            joined_on=today_dhaka(),
        )
        r = start_transfer(client_for(world["owner"]), sub.pk, member.pk)
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "transfer_not_allowed"

    def test_wrong_password(self, world):
        target = ensure_owner_seat(world)
        r = client_for(world["owner"]).post(
            f"/api/shared-plans/{world['plan_x'].pk}/transfer/",
            {"member_id": target.pk, "password": "wrong"},
            format="json",
        )
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "invalid_password"
        assert_error_shape(r)

    def test_duplicate_pending_409(self, world):
        target = ensure_owner_seat(world)
        client = client_for(world["owner"])
        assert start_transfer(client, world["plan_x"].pk, target.pk).status_code == 201
        r = start_transfer(client, world["plan_x"].pk, target.pk)
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "transfer_exists"

    def test_cancel_and_decline(self, world):
        target = ensure_owner_seat(world)
        client = client_for(world["owner"])
        tr_id = start_transfer(client, world["plan_x"].pk, target.pk).json()["id"]
        assert client_for(world["owner"]).post(f"/api/transfers/{tr_id}/cancel/").status_code == 200
        assert OwnershipTransfer.objects.get(pk=tr_id).status == TransferStatus.CANCELLED

        tr_id = start_transfer(client, world["plan_x"].pk, target.pk).json()["id"]
        assert client_for(world["member"]).post(f"/api/transfers/{tr_id}/decline/").status_code == 200
        assert OwnershipTransfer.objects.get(pk=tr_id).status == TransferStatus.DECLINED

    def test_accept_moves_owner(self, world):
        target = ensure_owner_seat(world)
        plan_id = world["plan_x"].pk
        client = client_for(world["owner"])
        tr_id = start_transfer(client, plan_id, target.pk).json()["id"]
        r = client_for(world["member"]).post(f"/api/transfers/{tr_id}/accept/")
        assert r.status_code == 200
        world["plan_x"].refresh_from_db()
        assert world["plan_x"].owner_id == world["member"].pk
        assert client_for(world["owner"]).get(f"/api/subscriptions/{plan_id}/").status_code == 404
        assert client_for(world["member"]).get(f"/api/subscriptions/{plan_id}/").status_code == 200

    def test_owner_detail_transfer_field(self, world):
        target = ensure_owner_seat(world)
        client = client_for(world["owner"])
        start_transfer(client, world["plan_x"].pk, target.pk)
        detail = client.get(f"/api/subscriptions/{world['plan_x'].pk}/").json()
        assert detail["transfer"] is not None
        assert detail["transfer"]["status"] == "pending"

    def test_incoming_transfer_on_member_detail(self, world):
        target = ensure_owner_seat(world)
        tr_id = start_transfer(client_for(world["owner"]), world["plan_x"].pk, target.pk).json()["id"]
        r = client_for(world["member"]).get(f"/api/me/shared-plans/{world['plan_x'].pk}/")
        assert r.status_code == 200, r.content
        row = r.json()
        assert row["incoming_transfer"]["id"] == tr_id

    def test_unauthenticated_401(self):
        assert APIClient().post("/api/transfers/1/accept/").status_code == 401
