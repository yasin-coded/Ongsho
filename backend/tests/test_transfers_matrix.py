from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditLog
from billing.models import Charge, ChargeStatus
from billing import services as billing_services
from core.dates import today_dhaka
from dues.models import Due, DueStatus
from notifications.models import Notification
from notifications.selectors import resolve_for_notifications
from payments.models import Payment, PaymentAllocation, ReviewStatus
from plans.models import Subscription
from sharing.models import Member, MemberStatus, OwnershipTransfer, TransferStatus

from core.exceptions import DomainError
from core.notify import notify
from sharing import ownership_transfer as xfer_service
from tests.helpers import run_concurrently
from tests.test_subscriptions import WORLD_PASS, assert_error_shape, client_for
from tests.test_transfers import ensure_owner_seat, start_transfer

User = get_user_model()
PASS = WORLD_PASS


def accept(client, tr_id):
    return client.post(f"/api/transfers/{tr_id}/accept/")


def cancel(client, tr_id):
    return client.post(f"/api/transfers/{tr_id}/cancel/")


def decline(client, tr_id):
    return client.post(f"/api/transfers/{tr_id}/decline/")


def transfer_notif_row(client, transfer_id: int):
    r = client.get("/api/notifications/?filter=all")
    assert r.status_code == 200
    for row in r.json().get("results", []):
        action = (row.get("payload") or {}).get("action") or {}
        if action.get("type") == "transfer" and action.get("transfer_id") == transfer_id:
            return row
    return None


def attention_transfers(client):
    r = client.get("/api/dashboard/summary/")
    assert r.status_code == 200
    return [x for x in r.json().get("attention", []) if x.get("kind") == "transfer"]


@pytest.mark.django_db
class TestTransferAcceptGuards:
    def test_accept_owner_changed(self, world):
        target = ensure_owner_seat(world)
        plan = world["plan_x"]
        tr_id = start_transfer(client_for(world["owner"]), plan.pk, target.pk).json()["id"]
        plan.owner = world["outsider"]
        plan.save(update_fields=["owner"])
        r = accept(client_for(world["member"]), tr_id)
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "owner_changed"
        assert_error_shape(r)

    def test_accept_target_left(self, world):
        target = ensure_owner_seat(world)
        tr_id = start_transfer(client_for(world["owner"]), world["plan_x"].pk, target.pk).json()["id"]
        target.status = MemberStatus.LEFT
        target.left_on = today_dhaka()
        target.save(update_fields=["status", "left_on"])
        r = accept(client_for(world["member"]), tr_id)
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "not_a_member"

    def test_accept_target_leave_requested(self, world):
        target = ensure_owner_seat(world)
        tr_id = start_transfer(client_for(world["owner"]), world["plan_x"].pk, target.pk).json()["id"]
        target.status = MemberStatus.LEAVE_REQUESTED
        target.save(update_fields=["status"])
        r = accept(client_for(world["member"]), tr_id)
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "not_a_member"

    def test_accept_archived_plan(self, world):
        target = ensure_owner_seat(world)
        plan = world["plan_x"]
        tr_id = start_transfer(client_for(world["owner"]), plan.pk, target.pk).json()["id"]
        plan.archived_on = timezone.now()
        plan.save(update_fields=["archived_on"])
        r = accept(client_for(world["member"]), tr_id)
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "transfer_closed"

    def test_accept_after_already_closed(self, world):
        target = ensure_owner_seat(world)
        owner = client_for(world["owner"])
        member = client_for(world["member"])
        tr_id = start_transfer(owner, world["plan_x"].pk, target.pk).json()["id"]
        assert cancel(owner, tr_id).status_code == 200
        r = accept(member, tr_id)
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "transfer_closed"


@pytest.mark.django_db(transaction=True)
class TestTransferConcurrency:
    def _svc_accept(self, user, tr_id):
        try:
            xfer_service.accept_ownership_transfer(user, tr_id, today=today_dhaka())
            return "ok"
        except DomainError as exc:
            return exc.code

    def _svc_cancel(self, user, tr_id):
        try:
            xfer_service.cancel_ownership_transfer(user, tr_id)
            return "ok"
        except DomainError as exc:
            return exc.code

    def test_two_concurrent_accepts(self, world):
        target = ensure_owner_seat(world)
        tr_id = start_transfer(client_for(world["owner"]), world["plan_x"].pk, target.pk).json()["id"]

        results, exceptions = run_concurrently(
            lambda: self._svc_accept(world["member"], tr_id),
            lambda: self._svc_accept(world["member"], tr_id),
            transaction=True,
        )
        assert not any(exceptions), exceptions
        assert results.count("ok") == 1
        assert "transfer_closed" in results
        assert OwnershipTransfer.objects.get(pk=tr_id).status == TransferStatus.ACCEPTED
        assert OwnershipTransfer.objects.filter(shared_plan=world["shared_x"], status=TransferStatus.PENDING).count() == 0

    def test_accept_races_cancel(self, world):
        target = ensure_owner_seat(world)
        tr_id = start_transfer(client_for(world["owner"]), world["plan_x"].pk, target.pk).json()["id"]

        results, exceptions = run_concurrently(
            lambda: self._svc_accept(world["member"], tr_id),
            lambda: self._svc_cancel(world["owner"], tr_id),
            transaction=True,
        )
        assert not any(exceptions), exceptions
        final = OwnershipTransfer.objects.get(pk=tr_id).status
        assert final in (TransferStatus.ACCEPTED, TransferStatus.CANCELLED)
        assert results.count("ok") == 1
        assert OwnershipTransfer.objects.filter(shared_plan=world["shared_x"], status=TransferStatus.PENDING).count() == 0


@pytest.mark.django_db
class TestTransferAfterAccept:
    def test_routes_and_member_rows_preserved(self, world):
        target = ensure_owner_seat(world)
        plan_id = world["plan_x"].pk
        shared = world["shared_x"]
        member_count_before = Member.objects.filter(shared_plan=shared).count()
        tr_id = start_transfer(client_for(world["owner"]), plan_id, target.pk).json()["id"]
        assert accept(client_for(world["member"]), tr_id).status_code == 200

        assert Member.objects.filter(shared_plan=shared).count() == member_count_before
        assert client_for(world["member"]).get(f"/api/subscriptions/{plan_id}/").status_code == 200
        assert client_for(world["owner"]).get(f"/api/subscriptions/{plan_id}/").status_code == 404
        assert client_for(world["owner"]).get(f"/api/me/shared-plans/{plan_id}/").status_code == 200
        assert client_for(world["member"]).get(f"/api/shared-plans/{plan_id}/ledger/").status_code == 200
        assert client_for(world["owner"]).get(f"/api/shared-plans/{plan_id}/ledger/").status_code == 404

    def test_dues_adjust_future_unlocked_not_locked(self, world):
        target = ensure_owner_seat(world)
        shared = world["shared_x"]
        owner_m = Member.objects.get(shared_plan=shared, user=world["owner"])
        today = world["today"]
        if not Member.objects.filter(shared_plan=shared, user=world["owner"]).exists():
            owner_m = Member.objects.create(
                shared_plan=shared,
                user=world["owner"],
                share_type=shared.split_type,
                status=MemberStatus.ACTIVE,
                joined_on=today,
            )
        future_start = today + timedelta(days=40)
        charge = Charge.objects.create(
            subscription=world["plan_x"],
            period_start=future_start,
            period_end=future_start + timedelta(days=29),
            due_date=future_start,
            amount=Decimal("1000.00"),
            amount_bdt=Decimal("1000.00"),
            status=ChargeStatus.UPCOMING,
            locked=False,
        )
        from dues import services as dues_services

        dues_services.create_dues_for_charge(charge)
        old_due = Due.objects.get(charge=charge, member=owner_m)
        new_due = Due.objects.get(charge=charge, member=target)
        old_due.status = DueStatus.PAID
        old_due.save(update_fields=["status"])
        new_due.status = DueStatus.DUE
        new_due.save(update_fields=["status"])

        locked_charge = Charge.objects.create(
            subscription=world["plan_x"],
            period_start=future_start + timedelta(days=31),
            period_end=future_start + timedelta(days=60),
            due_date=future_start + timedelta(days=31),
            amount=Decimal("500.00"),
            amount_bdt=Decimal("500.00"),
            status=ChargeStatus.UPCOMING,
            locked=True,
        )
        dues_services.create_dues_for_charge(locked_charge)
        locked_owner_due = Due.objects.get(charge=locked_charge, member=owner_m)
        locked_owner_due.status = DueStatus.PAID
        locked_owner_due.save(update_fields=["status"])
        locked_locked_status = locked_owner_due.status

        tr_id = start_transfer(client_for(world["owner"]), world["plan_x"].pk, target.pk).json()["id"]
        assert accept(client_for(world["member"]), tr_id).status_code == 200

        old_due.refresh_from_db()
        new_due.refresh_from_db()
        locked_owner_due.refresh_from_db()
        assert old_due.status == DueStatus.PAID
        assert new_due.status == DueStatus.DUE
        assert locked_owner_due.status == locked_locked_status
        assert AuditLog.objects.filter(action="transfer.accepted", plan_id=world["plan_x"].pk).exists()

    def test_waived_and_allocated_dues_untouched(self, world):
        target = ensure_owner_seat(world)
        shared = world["shared_x"]
        owner_m = Member.objects.get(shared_plan=shared, user=world["owner"])
        today = world["today"]
        future_start = today + timedelta(days=50)
        charge = Charge.objects.create(
            subscription=world["plan_x"],
            period_start=future_start,
            period_end=future_start + timedelta(days=29),
            due_date=future_start,
            amount=Decimal("800.00"),
            amount_bdt=Decimal("800.00"),
            status=ChargeStatus.UPCOMING,
            locked=False,
        )
        from dues import services as dues_services

        dues_services.create_dues_for_charge(charge)
        waived = Due.objects.get(charge=charge, member=target)
        waived.status = DueStatus.WAIVED
        waived.save(update_fields=["status"])
        alloc_due = Due.objects.get(charge=charge, member=owner_m)
        alloc_due.status = DueStatus.PAID
        alloc_due.save(update_fields=["status"])
        pay = Payment.objects.create(
            shared_plan=shared,
            member=owner_m,
            recorded_by=world["owner"],
            amount=alloc_due.amount_bdt,
            review_status=ReviewStatus.CONFIRMED,
        )
        PaymentAllocation.objects.create(payment=pay, due=alloc_due, amount_applied=alloc_due.amount_bdt)

        tr_id = start_transfer(client_for(world["owner"]), world["plan_x"].pk, target.pk).json()["id"]
        assert accept(client_for(world["member"]), tr_id).status_code == 200
        waived.refresh_from_db()
        alloc_due.refresh_from_db()
        assert waived.status == DueStatus.WAIVED
        assert alloc_due.status == DueStatus.PAID

    def test_pending_payment_and_leave_renotified(self, world):
        target = ensure_owner_seat(world)
        shared = world["shared_x"]
        plan_id = world["plan_x"].pk
        leaver = User.objects.create_user(
            email="leaver@example.com", password=PASS, name="Leaver", email_verified=True
        )
        leaver_member = Member.objects.create(
            shared_plan=shared,
            user=leaver,
            share_type=shared.split_type,
            status=MemberStatus.LEAVE_REQUESTED,
            joined_on=world["plan_x"].start_date,
        )
        notify(
            world["owner"],
            "leave_request",
            "Leaver wants to leave",
            world["plan_x"].plan_name,
            link=f"/app/plans/{plan_id}?leave={leaver_member.pk}",
            payload={
                "action": {"type": "leave", "member_id": leaver_member.pk, "plan_id": plan_id},
                "plan_id": plan_id,
            },
        )
        Payment.objects.create(
            shared_plan=shared,
            member=target,
            recorded_by=target.user,
            amount=Decimal("10.00"),
            review_status=ReviewStatus.PENDING,
        )
        notify(
            world["owner"],
            "payment_submitted",
            "Payment pending",
            "review",
            link=f"/app/plans/{plan_id}/review",
            payload={
                "action": {"type": "payment", "payment_id": Payment.objects.filter(shared_plan=shared).latest("pk").pk, "plan_id": plan_id},
                "plan_id": plan_id,
            },
        )
        old_leave_notes = list(
            Notification.objects.filter(user=world["owner"], kind="leave_request").values_list("pk", flat=True)
        )
        old_pay_notes = list(
            Notification.objects.filter(user=world["owner"], kind="payment_submitted").values_list("pk", flat=True)
        )
        owner_client = client_for(world["owner"])
        member_client = client_for(world["member"])
        tr_id = start_transfer(owner_client, plan_id, target.pk).json()["id"]
        assert accept(member_client, tr_id).status_code == 200

        new_owner_client = member_client
        pay_rows = [n for n in new_owner_client.get("/api/notifications/?filter=all").json()["results"] if n["kind"] == "payment_submitted"]
        assert pay_rows
        leave_rows = [n for n in new_owner_client.get("/api/notifications/?filter=all").json()["results"] if n["kind"] == "leave_request"]
        assert leave_rows
        for pk in old_leave_notes + old_pay_notes:
            assert Notification.objects.get(pk=pk).read_at is not None


@pytest.mark.django_db
class TestTransferNotificationsAndDashboard:
    def test_transfer_notification_resolved_states(self, world):
        target = ensure_owner_seat(world)
        owner = client_for(world["owner"])
        member = client_for(world["member"])
        tr_id = start_transfer(owner, world["plan_x"].pk, target.pk).json()["id"]
        row = transfer_notif_row(member, tr_id)
        assert row is not None
        assert row["resolved"] is None

        assert decline(member, tr_id).status_code == 200
        row = transfer_notif_row(member, tr_id)
        assert row["resolved"] == "declined"

        tr_id = start_transfer(owner, world["plan_x"].pk, target.pk).json()["id"]
        row = transfer_notif_row(member, tr_id)
        assert cancel(owner, tr_id).status_code == 200
        row = transfer_notif_row(member, tr_id)
        assert row["resolved"] == "cancelled"

        tr_id = start_transfer(owner, world["plan_x"].pk, target.pk).json()["id"]
        row = transfer_notif_row(member, tr_id)
        assert accept(member, tr_id).status_code == 200
        row = transfer_notif_row(member, tr_id)
        assert row["resolved"] == "accepted"

    def test_dashboard_attention_transfer_lifecycle(self, world):
        target = ensure_owner_seat(world)
        owner = client_for(world["owner"])
        member = client_for(world["member"])
        tr_id = start_transfer(owner, world["plan_x"].pk, target.pk).json()["id"]
        assert any(x.get("payload", {}).get("transfer_id") == tr_id for x in attention_transfers(member))

        assert decline(member, tr_id).status_code == 200
        assert not any(x.get("payload", {}).get("transfer_id") == tr_id for x in attention_transfers(member))

        tr_id = start_transfer(owner, world["plan_x"].pk, target.pk).json()["id"]
        assert attention_transfers(member)
        assert cancel(owner, tr_id).status_code == 200
        assert not attention_transfers(member)

        tr_id = start_transfer(owner, world["plan_x"].pk, target.pk).json()["id"]
        assert attention_transfers(member)
        assert accept(member, tr_id).status_code == 200
        assert not attention_transfers(member)


@pytest.mark.django_db
class TestTransferDeleteAndAudit:
    def test_delete_plan_cancels_pending_transfer(self, world):
        target = ensure_owner_seat(world)
        plan_id = world["plan_x"].pk
        tr_id = start_transfer(client_for(world["owner"]), plan_id, target.pk).json()["id"]
        r = client_for(world["owner"]).delete(
            f"/api/subscriptions/{plan_id}/",
            {"password": PASS},
            format="json",
        )
        assert r.status_code == 204
        assert AuditLog.objects.filter(action="transfer.cancelled", plan_id=plan_id).exists()
        assert not OwnershipTransfer.objects.filter(shared_plan=world["shared_x"], status=TransferStatus.PENDING).exists()

    def test_audit_on_start_cancel_decline_accept(self, world):
        target = ensure_owner_seat(world)
        owner = client_for(world["owner"])
        member = client_for(world["member"])
        plan_id = world["plan_x"].pk

        tr_id = start_transfer(owner, plan_id, target.pk).json()["id"]
        assert AuditLog.objects.filter(action="transfer.started", plan_id=plan_id).exists()
        assert cancel(owner, tr_id).status_code == 200
        assert AuditLog.objects.filter(action="transfer.cancelled", plan_id=plan_id).exists()

        tr_id = start_transfer(owner, plan_id, target.pk).json()["id"]
        assert decline(member, tr_id).status_code == 200
        assert AuditLog.objects.filter(action="transfer.declined", plan_id=plan_id).exists()

        tr_id = start_transfer(owner, plan_id, target.pk).json()["id"]
        assert accept(member, tr_id).status_code == 200
        assert AuditLog.objects.filter(action="transfer.accepted", plan_id=plan_id).exists()

    def test_matrix_endpoints_anonymous_401(self):
        client = APIClient()
        assert client.post("/api/transfers/1/accept/").status_code == 401
        assert client.post("/api/transfers/1/cancel/").status_code == 401
        assert client.post("/api/transfers/1/decline/").status_code == 401
        assert client.post("/api/shared-plans/1/transfer/", {}, format="json").status_code == 401