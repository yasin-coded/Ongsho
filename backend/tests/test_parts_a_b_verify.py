from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from audit.models import AuditLog
from catalog.models import Category, ServiceName
from core.choices import PaymentMethod
from core.dates import today_dhaka
from notifications.models import Notification
from plans.models import RenewalType, Subscription, SubscriptionStatus
from sharing.models import Invite, InviteStatus, Member, SharedPlan, SplitType

from tests.test_plan_status import client_for, make_subscription, post_status
from tests.test_subscriptions import client_for as sub_client_for, plan_payload


@pytest.mark.django_db
def test_a3_notification_title_payload_defaults(world):
    row = Notification.objects.create(user=world["owner"], kind="test", message="Hello")
    assert row.title == ""
    assert row.payload == {}


@pytest.mark.django_db
def test_a2_invite_replaces_member_nullable(world):
    invite = Invite.objects.create(
        shared_plan=world["shared_x"],
        invited_by=world["owner"],
        email="replace@example.com",
        token_hash="hash-replace",
        expires_on=timezone.now() + timedelta(days=7),
        status=InviteStatus.PENDING,
        replaces_member=world["due_x"].member,
    )
    assert invite.replaces_member_id == world["due_x"].member_id
    invite.replaces_member = None
    invite.save()
    assert invite.replaces_member_id is None


@pytest.mark.django_db
def test_b1_create_billing_from_and_anchor_from_trial(world):
    today = today_dhaka()
    trial_end = today + timedelta(days=7)
    client = sub_client_for(world["owner"])
    r = client.post(
        "/api/subscriptions/",
        plan_payload(start_date=str(today), trial_end_date=str(trial_end)),
        format="json",
    )
    assert r.status_code == 201
    assert r.json()["anchor_day"] == trial_end.day
    sub = Subscription.objects.get(pk=r.json()["id"])
    assert sub.billing_from == today
    assert sub.status == SubscriptionStatus.TRIAL


@pytest.mark.django_db
def test_b1_trial_inactive_on_trial_end_day(world):
    today = today_dhaka()
    client = sub_client_for(world["owner"])
    r = client.post(
        "/api/subscriptions/",
        plan_payload(start_date=str(today), trial_end_date=str(today)),
        format="json",
    )
    assert r.status_code == 201
    assert r.json()["status"] == SubscriptionStatus.ACTIVE


@pytest.mark.django_db
def test_b2_cancel_sets_cancelled_on(world):
    sub = make_subscription(world["owner"], status=SubscriptionStatus.ACTIVE)
    from core.schedule import next_due_date
    from billing.selectors import schedule_for_subscription

    expected = next_due_date(schedule_for_subscription(sub), today_dhaka())
    client = client_for(world["owner"])
    assert post_status(client, sub.pk, "cancel").status_code == 200
    sub.refresh_from_db()
    assert sub.cancelled_on == expected


@pytest.mark.django_db
def test_b2_resume_sets_billing_from(world):
    sub = make_subscription(world["owner"], status=SubscriptionStatus.PAUSED)
    before = sub.billing_from
    client = client_for(world["owner"])
    post_status(client, sub.pk, "resume")
    sub.refresh_from_db()
    assert sub.billing_from == today_dhaka()
    assert sub.paused_on is None
    assert before != sub.billing_from or before == today_dhaka()


@pytest.mark.django_db
def test_b3_trial_rule_on_resume_and_renew(world):
    client = client_for(world["owner"])
    trial_end = today_dhaka() + timedelta(days=5)
    sub = make_subscription(
        world["owner"],
        status=SubscriptionStatus.PAUSED,
        trial_end_date=trial_end,
    )
    assert post_status(client, sub.pk, "resume").json()["status"] == SubscriptionStatus.TRIAL

    sub_today = make_subscription(
        world["owner"],
        status=SubscriptionStatus.PAUSED,
        trial_end_date=today_dhaka(),
        renewal_type=RenewalType.FIXED_TERM,
        end_date=today_dhaka() + timedelta(days=30),
    )
    assert post_status(client, sub_today.pk, "resume").json()["status"] == SubscriptionStatus.ACTIVE

    expired = make_subscription(
        world["owner"],
        status=SubscriptionStatus.EXPIRED,
        trial_end_date=trial_end,
        renewal_type=RenewalType.FIXED_TERM,
        end_date=today_dhaka() - timedelta(days=1),
    )
    new_end = today_dhaka() + timedelta(days=90)
    body = post_status(client, expired.pk, "renew", {"end_date": str(new_end)}).json()
    assert body["status"] == SubscriptionStatus.TRIAL


@pytest.mark.django_db
def test_b4_audit_summary_and_plan_id_on_pause(world):
    sub = make_subscription(world["owner"], status=SubscriptionStatus.ACTIVE)
    client = client_for(world["owner"])
    post_status(client, sub.pk, "pause")
    row = AuditLog.objects.get(entity_id=sub.pk, action="plan.paused")
    assert row.plan_id == sub.pk
    assert "paused" in row.summary.lower()


@pytest.mark.django_db
def test_b4_plan_created_summary(world):
    client = sub_client_for(world["owner"])
    r = client.post("/api/subscriptions/", plan_payload(plan_name="Audit Name"), format="json")
    row = AuditLog.objects.get(action="plan.created", entity_id=r.json()["id"])
    assert row.plan_id == r.json()["id"]
    assert "You created Audit Name" in row.summary


@pytest.mark.django_db
def test_b5_list_counts_and_needs_review(world):
    from payments.models import Payment, ReviewStatus

    client = sub_client_for(world["owner"])
    client.post("/api/subscriptions/", plan_payload(plan_name="Rare"), format="json")
    Subscription.objects.filter(owner=world["owner"], plan_name="Rare").update(rarely_used=True)
    pay = Payment.objects.create(
        shared_plan=world["shared_x"],
        member=world["due_x"].member,
        recorded_by=world["owner"],
        method=PaymentMethod.BKASH,
        amount=Decimal("10.00"),
        review_status=ReviewStatus.PENDING,
    )
    assert pay.pk
    listing = client.get("/api/subscriptions/").json()
    assert set(listing["counts"].keys()) == {"all", "review", "rarely"}
    assert listing["counts"]["review"] >= 1
    filtered = client.get("/api/subscriptions/?needs_review=true").json()
    assert any(p["id"] == world["plan_x"].pk for p in filtered["results"])
    bad = client.get("/api/subscriptions/?needs_review=maybe")
    assert bad.status_code == 400


@pytest.mark.django_db
def test_b5_detail_pending_invites_and_member_count(world):
    Invite.objects.create(
        shared_plan=world["shared_x"],
        invited_by=world["owner"],
        email="pending@example.com",
        token_hash="hash-pending",
        expires_on=timezone.now() + timedelta(days=3),
        status=InviteStatus.PENDING,
    )
    client = sub_client_for(world["owner"])
    detail = client.get(f"/api/subscriptions/{world['plan_x'].pk}/").json()
    assert "pending@example.com" in detail["pending_invites"]
    assert detail["member_count"] == 2
