from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.models import Category, ServiceName
from core.choices import Currency, PaymentMethod
from core.dates import today_dhaka
from core.notify import notify, resolve_notifications
from notifications.kinds import REMINDER_KINDS, group_of, validate_kind
from notifications.models import Notification
from notifications.selectors import resolve_for_notifications
from payments.models import Payment, ReviewStatus
from plans.models import CycleUnit, PlanMode, RenewalType, Subscription, SubscriptionStatus
from sharing.models import (
    Invite,
    InviteStatus,
    Member,
    MemberStatus,
    OwnershipTransfer,
    SharedPlan,
    SplitType,
    TransferStatus,
)

User = get_user_model()
STRONG = "HorseBatteryStaple99"


def assert_error_shape(response):
    assert response.status_code >= 400
    data = response.json()
    assert set(data) == {"error"}
    assert set(data["error"]) == {"code", "message", "fields"}


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def plan_bundle(db):
    streaming = Category.objects.get(is_preset=True, name="Streaming")
    netflix = ServiceName.objects.filter(is_preset=True, name="Netflix", category=streaming).first()
    owner = User.objects.create_user(
        email="notif-owner@example.com", password=STRONG, name="Owner", email_verified=True
    )
    member = User.objects.create_user(
        email="notif-member@example.com", password=STRONG, name="Member", email_verified=True
    )
    sub = Subscription.objects.create(
        owner=owner,
        service_name=netflix,
        category=streaming,
        plan_name="Notify Plan",
        plan_mode=PlanMode.OWNER,
        currency=Currency.BDT,
        cycle_unit=CycleUnit.MONTH,
        cycle_count=1,
        anchor_day=5,
        start_date="2020-01-05",
        renewal_type=RenewalType.AUTO,
        status=SubscriptionStatus.ACTIVE,
        recommended_method=PaymentMethod.BKASH,
        billing_from=today_dhaka(),
    )
    shared = SharedPlan.objects.create(subscription=sub, split_type=SplitType.EQUAL, seats=3)
    Member.objects.create(
        shared_plan=shared,
        user=owner,
        share_type=SplitType.EQUAL,
        status=MemberStatus.ACTIVE,
        joined_on=today_dhaka(),
    )
    member_row = Member.objects.create(
        shared_plan=shared,
        user=member,
        share_type=SplitType.EQUAL,
        status=MemberStatus.ACTIVE,
        joined_on=today_dhaka(),
    )
    return {
        "owner": owner,
        "member": member,
        "shared_plan": shared,
        "member_row": member_row,
        "subscription": sub,
    }


def action_payload(action_type, **ids):
    action = {"type": action_type, **ids}
    if "plan_id" in ids:
        payload = {"action": action, "plan_id": ids["plan_id"]}
    else:
        payload = {"action": action}
    return payload


class TestKindsAndNotify:
    def test_group_mapping(self):
        assert group_of("payment_submitted") == "payments"
        assert group_of("due_soon") == "reminders"
        assert group_of("invite") == "plans"
        assert group_of("email_changed") == "account"

    def test_unknown_kind_raises(self):
        with pytest.raises(ValueError, match="Unknown notification kind"):
            group_of("not_a_kind")
        with pytest.raises(ValueError, match="Unknown notification kind"):
            validate_kind("bogus")

    @pytest.mark.django_db
    def test_notify_creates_row(self):
        user = User.objects.create_user(
            email="n1@example.com", password=STRONG, name="N", email_verified=True
        )
        row = notify(user, "due_soon", "Due soon", "Pay ৳100", link="/app/x", payload={"plan_id": 1})
        assert row.pk
        assert row.kind == "due_soon"
        assert row.title == "Due soon"

    @pytest.mark.django_db
    def test_notify_invalid_kind(self):
        user = User.objects.create_user(
            email="n2@example.com", password=STRONG, name="N", email_verified=True
        )
        with pytest.raises(ValidationError):
            notify(user, "bad_kind", "T", "m")

    @pytest.mark.django_db
    def test_notify_title_too_long(self):
        user = User.objects.create_user(
            email="n3@example.com", password=STRONG, name="N", email_verified=True
        )
        with pytest.raises(ValidationError):
            notify(user, "due_soon", "x" * 121, "m")


@pytest.mark.django_db
class TestResolvedStates:
    def test_payment_states(self, plan_bundle):
        owner = plan_bundle["owner"]
        shared = plan_bundle["shared_plan"]
        member_row = plan_bundle["member_row"]
        member = plan_bundle["member"]

        def pay(status):
            return Payment.objects.create(
                shared_plan=shared,
                member=member_row,
                recorded_by=member,
                method=PaymentMethod.BKASH,
                amount=Decimal("100.00"),
                review_status=status,
            )

        cases = [
            (ReviewStatus.PENDING, None),
            (ReviewStatus.CONFIRMED, "approved"),
            (ReviewStatus.REJECTED, "rejected"),
            (ReviewStatus.REVERSED, "reversed"),
        ]
        for review_status, expected in cases:
            payment = pay(review_status)
            note = Notification.objects.create(
                user=owner,
                kind="payment_submitted",
                title="Review",
                message="m",
                payload=action_payload("payment", payment_id=payment.pk, plan_id=plan_bundle["subscription"].pk),
            )
            resolved = resolve_for_notifications([note])[note.pk]
            assert resolved == expected

        gone = Notification.objects.create(
            user=owner,
            kind="payment_submitted",
            title="Gone",
            message="m",
            payload=action_payload("payment", payment_id=999999, plan_id=1),
        )
        assert resolve_for_notifications([gone])[gone.pk] == "gone"

    def test_invite_states(self, plan_bundle):
        owner = plan_bundle["owner"]
        shared = plan_bundle["shared_plan"]
        now = timezone.now()

        invite = Invite.objects.create(
            shared_plan=shared,
            invited_by=owner,
            email="inv@example.com",
            token_hash="hash-inv",
            expires_on=now + timedelta(days=1),
            status=InviteStatus.PENDING,
        )
        note = Notification.objects.create(
            user=owner,
            kind="invite",
            title="Invite",
            message="m",
            payload=action_payload("invite", invite_id=invite.pk, plan_id=plan_bundle["subscription"].pk),
        )
        assert resolve_for_notifications([note])[note.pk] is None

        invite.expires_on = now - timedelta(hours=1)
        invite.save(update_fields=["expires_on"])
        assert resolve_for_notifications([note])[note.pk] == "expired"

        invite.status = InviteStatus.ACCEPTED
        invite.save(update_fields=["status"])
        assert resolve_for_notifications([note])[note.pk] == "joined"

        invite.status = InviteStatus.DECLINED
        invite.save(update_fields=["status"])
        assert resolve_for_notifications([note])[note.pk] == "declined"

        invite.status = InviteStatus.CANCELLED
        invite.save(update_fields=["status"])
        assert resolve_for_notifications([note])[note.pk] == "cancelled"

    def test_leave_states(self, plan_bundle):
        owner = plan_bundle["owner"]
        member_row = plan_bundle["member_row"]

        note = Notification.objects.create(
            user=owner,
            kind="leave_request",
            title="Leave",
            message="m",
            payload=action_payload("leave", member_id=member_row.pk, plan_id=plan_bundle["subscription"].pk),
        )
        member_row.status = MemberStatus.LEAVE_REQUESTED
        member_row.save(update_fields=["status"])
        assert resolve_for_notifications([note])[note.pk] is None

        member_row.status = MemberStatus.LEFT
        member_row.save(update_fields=["status"])
        assert resolve_for_notifications([note])[note.pk] == "approved"

        member_row.status = MemberStatus.ACTIVE
        member_row.save(update_fields=["status"])
        assert resolve_for_notifications([note])[note.pk] == "declined"

    def test_transfer_states(self, plan_bundle):
        owner = plan_bundle["owner"]
        member = plan_bundle["member"]
        shared = plan_bundle["shared_plan"]

        transfer = OwnershipTransfer.objects.create(
            shared_plan=shared,
            from_user=owner,
            to_user=member,
            status=TransferStatus.PENDING,
        )
        note = Notification.objects.create(
            user=owner,
            kind="transfer",
            title="Xfer",
            message="m",
            payload=action_payload("transfer", transfer_id=transfer.pk, plan_id=plan_bundle["subscription"].pk),
        )
        assert resolve_for_notifications([note])[note.pk] is None

        transfer.status = TransferStatus.ACCEPTED
        transfer.save(update_fields=["status"])
        assert resolve_for_notifications([note])[note.pk] == "accepted"

        transfer.status = TransferStatus.DECLINED
        transfer.save(update_fields=["status"])
        assert resolve_for_notifications([note])[note.pk] == "declined"

        transfer.status = TransferStatus.CANCELLED
        transfer.save(update_fields=["status"])
        assert resolve_for_notifications([note])[note.pk] == "cancelled"


@pytest.mark.django_db
class TestNotificationApi:
    NOTIF_ENDPOINTS = [
        ("/api/notifications/", "get"),
        ("/api/notifications/read-all/", "post"),
    ]

    @pytest.mark.parametrize("path,method", NOTIF_ENDPOINTS)
    def test_anonymous_401(self, path, method):
        client = APIClient()
        call = getattr(client, method)
        response = call(path, {} if method == "post" else None, format="json") if method == "post" else call(path)
        assert response.status_code == 401
        assert_error_shape(response)

    def test_invalid_filter(self):
        user = User.objects.create_user(
            email="nf@example.com", password=STRONG, name="N", email_verified=True
        )
        response = client_for(user).get("/api/notifications/?filter=invalid")
        assert response.status_code == 400
        assert "filter" in response.json()["error"]["fields"]

    def test_scoping_and_mark_read_404(self, plan_bundle):
        owner = plan_bundle["owner"]
        other = User.objects.create_user(
            email="other-n@example.com", password=STRONG, name="O", email_verified=True
        )
        note = Notification.objects.create(user=owner, kind="due_soon", title="T", message="m")
        assert client_for(other).post(f"/api/notifications/{note.pk}/read/", {}, format="json").status_code == 404

    def test_filters_counts_pagination(self, plan_bundle):
        owner = plan_bundle["owner"]
        Notification.objects.create(user=owner, kind="payment_submitted", title="P", message="m")
        Notification.objects.create(user=owner, kind="invite", title="I", message="m")
        Notification.objects.create(user=owner, kind="due_soon", title="R", message="m")
        Notification.objects.create(user=owner, kind="email_changed", title="E", message="m")
        payment = Payment.objects.create(
            shared_plan=plan_bundle["shared_plan"],
            member=plan_bundle["member_row"],
            recorded_by=plan_bundle["member"],
            method=PaymentMethod.BKASH,
            amount=Decimal("10"),
            review_status=ReviewStatus.PENDING,
        )
        pending = Notification.objects.create(
            user=owner,
            kind="payment_submitted",
            title="Act",
            message="m",
            payload=action_payload(
                "payment", payment_id=payment.pk, plan_id=plan_bundle["subscription"].pk
            ),
        )
        data = client_for(owner).get("/api/notifications/").json()
        assert data["counts"]["all"] == 5
        assert data["counts"]["payments"] == 2
        assert data["counts"]["plans"] == 1
        assert data["counts"]["reminders"] == 1
        assert data["counts"]["action"] == 1
        assert data["unread"] == 5
        kinds = {row["kind"] for row in data["results"]}
        assert "email_changed" in kinds

        payments = client_for(owner).get("/api/notifications/?filter=payments").json()
        assert all(row["group"] == "payments" for row in payments["results"])
        assert "email_changed" not in {row["kind"] for row in payments["results"]}

        page = client_for(owner).get("/api/notifications/?page_size=2&page=2").json()
        assert len(page["results"]) == 2
        assert page["counts"]["all"] == 5

        action_only = client_for(owner).get("/api/notifications/?filter=action").json()
        assert len(action_only["results"]) == 1
        assert action_only["results"][0]["id"] == pending.pk
        assert action_only["results"][0]["needs_action"] is True

    def test_needs_action_and_resolved_on_list(self, plan_bundle):
        owner = plan_bundle["owner"]
        shared = plan_bundle["shared_plan"]
        payment = Payment.objects.create(
            shared_plan=shared,
            member=plan_bundle["member_row"],
            recorded_by=plan_bundle["member"],
            method=PaymentMethod.BKASH,
            amount=Decimal("50"),
            review_status=ReviewStatus.PENDING,
        )
        Notification.objects.create(
            user=owner,
            kind="payment_submitted",
            title="Review",
            message="m",
            payload=action_payload("payment", payment_id=payment.pk, plan_id=plan_bundle["subscription"].pk),
        )
        row = client_for(owner).get("/api/notifications/").json()["results"][0]
        assert row["needs_action"] is True
        assert row["resolved"] is None

        payment.review_status = ReviewStatus.CONFIRMED
        payment.save(update_fields=["review_status"])
        row2 = client_for(owner).get("/api/notifications/").json()["results"][0]
        assert row2["needs_action"] is False
        assert row2["resolved"] == "approved"

    def test_mark_read_idempotent(self, plan_bundle):
        owner = plan_bundle["owner"]
        note = Notification.objects.create(user=owner, kind="renewal", title="T", message="m")
        client = client_for(owner)
        first = client.post(f"/api/notifications/{note.pk}/read/", {}, format="json")
        assert first.status_code == 200
        read_at = first.json()["read_at"]
        second = client.post(f"/api/notifications/{note.pk}/read/", {}, format="json")
        assert second.status_code == 200
        assert second.json()["read_at"] == read_at

    def test_read_all(self, plan_bundle):
        owner = plan_bundle["owner"]
        Notification.objects.create(user=owner, kind="renewal", title="A", message="m")
        Notification.objects.create(user=owner, kind="trial_end", title="B", message="m")
        client = client_for(owner)
        first = client.post("/api/notifications/read-all/", {}, format="json")
        assert first.status_code == 200
        assert first.json()["updated"] == 2
        second = client.post("/api/notifications/read-all/", {}, format="json")
        assert second.json()["updated"] == 0

    def test_delete_own_notification(self, plan_bundle):
        owner = plan_bundle["owner"]
        member = plan_bundle["member"]
        note = Notification.objects.create(user=owner, kind="renewal", title="Drop me", message="m")
        Notification.objects.create(user=member, kind="renewal", title="Keep", message="m")
        client = client_for(owner)
        assert client.delete(f"/api/notifications/{note.pk}/").status_code == 204
        assert not Notification.objects.filter(pk=note.pk).exists()
        assert Notification.objects.filter(user=member).count() == 1
        assert client_for(member).delete(f"/api/notifications/{note.pk}/").status_code == 404


@pytest.mark.django_db
class TestResolveNotifications:
    def test_marks_only_matching_unread(self, plan_bundle):
        owner = plan_bundle["owner"]
        payload = action_payload("payment", payment_id=42, plan_id=1)
        n1 = Notification.objects.create(
            user=owner, kind="payment_submitted", title="1", message="m", payload=payload
        )
        n2 = Notification.objects.create(
            user=owner,
            kind="payment_submitted",
            title="2",
            message="m",
            payload=action_payload("payment", payment_id=99, plan_id=1),
        )
        updated = resolve_notifications("payment", payment_id=42)
        assert updated == 1
        n1.refresh_from_db()
        n2.refresh_from_db()
        assert n1.read_at is not None
        assert n2.read_at is None


@pytest.mark.django_db
def test_list_query_count_stable_with_25_notifications(plan_bundle):
    owner = plan_bundle["owner"]
    kinds = list(REMINDER_KINDS) * 7
    for i in range(25):
        kind = kinds[i % len(kinds)]
        payload = {}
        if i % 5 == 0:
            payload = action_payload("payment", payment_id=1, plan_id=1)
        Notification.objects.create(user=owner, kind=kind, title=f"T{i}", message="m", payload=payload)
    client = client_for(owner)
    with CaptureQueriesContext(connection) as ctx:
        response = client.get("/api/notifications/?page_size=25")
    assert response.status_code == 200
    assert len(ctx.captured_queries) <= 18


@pytest.mark.django_db
class TestEmailChangeNotifications:
    @pytest.fixture(autouse=True)
    def mail_settings(self, settings):
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
        settings.FRONTEND_BASE_URL = "http://localhost:5173"

    def test_request_and_verify_create_notifications(self):
        user = User.objects.create_user(
            email="ec@example.com", password=STRONG, name="EC", email_verified=True
        )
        client = client_for(user)
        client.post(
            "/api/me/email/", {"new_email": "ec-new@example.com", "password": STRONG}, format="json"
        )
        kinds = list(
            Notification.objects.filter(user=user).values_list("kind", "title", flat=False)
        )
        assert ("email_changed", "Confirm your new email") in kinds

        user.pending_email = "ec-new@example.com"
        user.save(update_fields=["pending_email"])
        from accounts.tokens import make_email_change_token

        token = make_email_change_token(user, "ec-new@example.com")
        client.post("/api/me/email/verify/", {"token": token}, format="json")
        titles = list(Notification.objects.filter(user=user).values_list("title", flat=True))
        assert "Your email was changed" in titles
