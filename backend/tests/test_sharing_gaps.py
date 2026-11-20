from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import connection
from django.utils import timezone

from accounts.cookies import REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH
from billing import services as billing_services
from billing.models import Charge
from core.dates import today_dhaka
from notifications.models import Notification
from core.choices import PaymentMethod
from payments.models import Payment, ReviewStatus
from plans.models import PlanMode, PriceChange, Subscription
from sharing.models import Invite, InviteStatus, Member, MemberStatus, SharedPlan, SplitType
from sharing import services as sharing_services

from tests.test_subscriptions import WORLD_PASS, client_for, make_payment, plan_payload

User = get_user_model()
STRONG = "HorseBatteryStaple99"


def _invite_token(owner_client, plan_id: int, email: str) -> tuple[int, str]:
    r = owner_client.post(
        f"/api/shared-plans/{plan_id}/invites/",
        {"email": email},
        format="json",
    )
    assert r.status_code == 201, r.content
    raw = r.json()["link"].split("/")[-1]
    return r.json()["id"], raw


def _notif_resolved(user, invite_id: int) -> str | None:
    body = client_for(user).get("/api/notifications/").json()
    for row in body.get("results", []):
        action = row.get("payload", {}).get("action") or {}
        if row.get("kind") == "invite" and action.get("invite_id") == invite_id:
            return row.get("resolved")
    return None


def _leave_notif_resolved(owner, member_id: int) -> str | None:
    body = client_for(owner).get("/api/notifications/").json()
    for row in body["results"]:
        action = row.get("payload", {}).get("action") or {}
        if row.get("kind") == "leave_request" and action.get("member_id") == member_id:
            return row.get("resolved")
    return None


@pytest.fixture(autouse=True)
def sharing_mail(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.FRONTEND_BASE_URL = "http://localhost:5173"


@pytest.fixture
def roomy_plan(world):
    """Shared plan with spare seats for invite flows (world plan_x has only one open slot)."""
    r = client_for(world["owner"]).post(
        "/api/subscriptions/",
        {**plan_payload(plan_name="Roomy Invites"), "seats": 8},
        format="json",
    )
    assert r.status_code == 201
    return r.json()["id"]


@pytest.mark.django_db(transaction=True)
def test_concurrent_accept_one_invite_one_member(world):
    email = "race-accept@example.com"
    joiner = User.objects.create_user(
        email=email, password=STRONG, name="Racer", email_verified=True
    )
    owner_client = client_for(world["owner"])
    _, token = _invite_token(owner_client, world["plan_x"].pk, email)
    today = world["today"]
    from sharing import services

    from tests.helpers import run_concurrently

    def accept():
        return services.accept_invite(joiner, token=token, today=today)

    results, errors = run_concurrently([accept, accept])
    ok = [r for r in results if r is not None]
    bad = [e for e in errors if e is not None]
    assert len(ok) == 1
    assert len(bad) == 1
    assert bad[0].code == "invite_used"
    assert Member.objects.filter(shared_plan=world["shared_x"], user=joiner).count() == 1


@pytest.mark.django_db
def test_replacement_copies_share_and_marks_left(world):
    today = world["today"]
    old = world["member_row"]
    old.share_type = SplitType.CUSTOM
    old.share_value = Decimal("25.00")
    old.save(update_fields=["share_type", "share_value"])
    replacement_email = "replacement@example.com"
    new_user = User.objects.create_user(
        email=replacement_email, password=STRONG, name="New", email_verified=True
    )
    owner = client_for(world["owner"])
    r = owner.post(
        f"/api/members/{old.pk}/replace/",
        {"email": replacement_email},
        format="json",
    )
    assert r.status_code == 201
    token = r.json()["link"].split("/")[-1]
    assert client_for(new_user).post(f"/api/invites/{token}/accept/", {}, format="json").status_code == 200
    old.refresh_from_db()
    new_row = Member.objects.get(shared_plan=world["shared_x"], user=new_user)
    assert new_row.share_type == SplitType.CUSTOM
    assert new_row.share_value == Decimal("25.00")
    assert old.status == MemberStatus.LEFT
    assert old.left_on == today


@pytest.mark.django_db
def test_invite_signup_sets_tokens(world):
    email = "brand-new-invite@example.com"
    _, token = _invite_token(client_for(world["owner"]), world["plan_x"].pk, email)
    from rest_framework.test import APIClient

    client = APIClient()
    r = client.post(
        f"/api/invites/{token}/signup/",
        {"name": "Fresh", "password": STRONG},
        format="json",
    )
    assert r.status_code == 201
    assert "access" in r.json()
    cookie = r.cookies.get(REFRESH_COOKIE_NAME)
    assert cookie is not None
    assert cookie["path"] == REFRESH_COOKIE_PATH
    assert cookie["httponly"]
    assert User.objects.filter(email=email, email_verified=True).exists()
    assert Member.objects.filter(shared_plan=world["shared_x"], user__email=email).exists()


@pytest.mark.django_db
def test_invite_cancel_decline_accept_by_id_and_new_link(world, roomy_plan):
    owner = client_for(world["owner"])
    plan_id = roomy_plan

    cancel_email = "cancel-me@example.com"
    invite_id, cancel_token = _invite_token(owner, plan_id, cancel_email)
    User.objects.create_user(email=cancel_email, password=STRONG, name="C", email_verified=True)
    assert owner.post(f"/api/invites/{invite_id}/cancel/", {}, format="json").status_code == 200
    assert client_for(User.objects.get(email=cancel_email)).post(
        f"/api/invites/{cancel_token}/accept/", {}, format="json"
    ).status_code in (404, 409)

    decline_email = "decline-me@example.com"
    d_id, d_token = _invite_token(owner, plan_id, decline_email)
    decliner = User.objects.create_user(email=decline_email, password=STRONG, name="D", email_verified=True)
    assert client_for(decliner).post(f"/api/invites/{d_token}/decline/", {}, format="json").status_code == 200
    assert Invite.objects.get(pk=d_id).status == InviteStatus.DECLINED

    accept_email = "by-id@example.com"
    a_id, a_token = _invite_token(owner, plan_id, accept_email)
    accepter = User.objects.create_user(email=accept_email, password=STRONG, name="A", email_verified=True)
    assert client_for(accepter).post(f"/api/me/invites/{a_id}/accept/", {}, format="json").status_code == 200

    link_email = "new-link@example.com"
    link_id, old_token = _invite_token(owner, plan_id, link_email)
    link_user = User.objects.create_user(email=link_email, password=STRONG, name="L", email_verified=True)
    renew = owner.post(f"/api/invites/{link_id}/new-link/", {}, format="json")
    assert renew.status_code == 200
    new_token = renew.json()["link"].split("/")[-1]
    assert client_for(link_user).post(f"/api/invites/{old_token}/accept/", {}, format="json").status_code in (404, 409)
    assert client_for(link_user).post(f"/api/invites/{new_token}/accept/", {}, format="json").status_code in (200, 409)


@pytest.mark.django_db
def test_reseller_no_owner_seat_seats_are_buyers(world):
    client = client_for(world["owner"])
    r = client.post(
        "/api/subscriptions/",
        {**plan_payload(plan_name="Resell"), "plan_mode": PlanMode.RESELLER, "seats": 2},
        format="json",
    )
    assert r.status_code == 201
    shared = SharedPlan.objects.get(subscription_id=r.json()["id"])
    assert not Member.objects.filter(shared_plan=shared, user=world["owner"]).exists()
    assert shared.seats == 2


@pytest.mark.django_db
def test_invite_capacity_and_duplicate_edges(world):
    owner = client_for(world["owner"])
    tight = owner.post(
        "/api/subscriptions/",
        {**plan_payload(plan_name="Tight"), "seats": 2},
        format="json",
    )
    assert tight.status_code == 201
    plan_id = tight.json()["id"]
    full = owner.post(f"/api/shared-plans/{plan_id}/invites/", {"email": "seat1@x.com"}, format="json")
    assert full.status_code == 201
    blocked = owner.post(f"/api/shared-plans/{plan_id}/invites/", {"email": "seat2@x.com"}, format="json")
    assert blocked.status_code in (400, 409)
    dup = owner.post(f"/api/shared-plans/{plan_id}/invites/", {"email": "seat1@x.com"}, format="json")
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "invite_exists"
    member_dup = owner.post(
        f"/api/shared-plans/{plan_id}/invites/",
        {"email": world["member"].email},
        format="json",
    )
    assert member_dup.status_code == 400


@pytest.mark.django_db
def test_plan_delete_hook_erased_and_archived(world):
    today = world["today"]
    erase = client_for(world["owner"]).post(
        "/api/subscriptions/",
        {**plan_payload(plan_name="EraseMe"), "seats": 3},
        format="json",
    )
    erase_id = erase.json()["id"]
    erase_shared = SharedPlan.objects.get(subscription_id=erase_id)
    wipee = User.objects.create_user(
        email="erase-member@example.com", password=STRONG, name="EM", email_verified=True
    )
    etok = _invite_token(client_for(world["owner"]), erase_id, wipee.email)[1]
    client_for(wipee).post(f"/api/invites/{etok}/accept/", {}, format="json")
    pending = _invite_token(client_for(world["owner"]), erase_id, "pending-erase@example.com")
    invite_pk = pending[0]
    assert Invite.objects.filter(pk=invite_pk, status=InviteStatus.PENDING).exists()
    r = client_for(world["owner"]).delete(
        f"/api/subscriptions/{erase_id}/",
        {"password": WORLD_PASS},
        format="json",
    )
    assert r.status_code == 204
    assert not Subscription.objects.filter(pk=erase_id).exists()
    assert not Invite.objects.filter(pk=invite_pk).exists()
    assert Notification.objects.filter(
        user=wipee, kind="plan_deleted", message__icontains="removed for everyone"
    ).exists()

    arch = client_for(world["owner"]).post(
        "/api/subscriptions/",
        {**plan_payload(plan_name="ArchiveMe"), "seats": 3},
        format="json",
    )
    assert arch.status_code == 201
    arch_id = arch.json()["id"]
    arch_shared = SharedPlan.objects.get(subscription_id=arch_id)
    arch_member = User.objects.create_user(
        email="arch-member@example.com", password=STRONG, name="AM", email_verified=True
    )
    atok = _invite_token(client_for(world["owner"]), arch_id, arch_member.email)[1]
    client_for(arch_member).post(f"/api/invites/{atok}/accept/", {}, format="json")
    arch_mem_row = arch_shared.members.get(user=arch_member)
    Payment.objects.create(
        shared_plan=arch_shared,
        member=arch_mem_row,
        recorded_by=world["owner"],
        method=PaymentMethod.BKASH,
        amount=Decimal("50.00"),
        review_status=ReviewStatus.CONFIRMED,
    )
    from plans import services as plan_services

    assert plan_services._plan_has_confirmed_or_reversed_payment(Subscription.objects.get(pk=arch_id))
    invite_arch = Invite.objects.create(
        shared_plan=arch_shared,
        invited_by=world["member"],
        email="arch-inv@example.com",
        token_hash="hash-arch",
        expires_on=timezone.now() + timedelta(days=2),
        status=InviteStatus.PENDING,
    )
    assert client_for(world["owner"]).delete(
        f"/api/subscriptions/{arch_id}/",
        {"password": WORLD_PASS},
        format="json",
    ).status_code == 204
    arch_sub = Subscription.all_with_archived.get(pk=arch_id)
    assert arch_sub.archived_on is not None
    invite_arch.refresh_from_db()
    assert invite_arch.status == InviteStatus.CANCELLED
    assert Notification.objects.filter(
        user=arch_member, kind="plan_deleted", message__icontains="payment history"
    ).exists()


@pytest.mark.django_db
def test_price_change_wording_equal_and_custom(world):
    today = world["today"]
    eff = today + timedelta(days=1)
    owner = client_for(world["owner"])
    plan_id = world["plan_x"].pk
    r = owner.post(
        f"/api/subscriptions/{plan_id}/price-changes/",
        {"amount": "150.00", "effective_from": str(eff)},
        format="json",
    )
    assert r.status_code == 201
    note = Notification.objects.filter(user=world["member"], kind="price_change").latest("id")
    assert "seats moves" in note.message.lower()

    c_email = "custom-member@example.com"
    custom_member = User.objects.create_user(email=c_email, password=STRONG, name="CM", email_verified=True)
    custom = client_for(world["owner"]).post(
        "/api/subscriptions/",
        {**plan_payload(plan_name="Custom Price"), "seats": 2, "split_type": "custom"},
        format="json",
    )
    cid = custom.json()["id"]
    cshared = SharedPlan.objects.get(subscription_id=cid)
    cshared.split_type = SplitType.CUSTOM
    cshared.save(update_fields=["split_type"])
    ctok = _invite_token(owner, cid, c_email)[1]
    client_for(custom_member).post(f"/api/invites/{ctok}/accept/", {}, format="json")
    eff2 = today + timedelta(days=2)
    assert owner.post(
        f"/api/subscriptions/{cid}/price-changes/",
        {"amount": "120.00", "effective_from": str(eff2)},
        format="json",
    ).status_code == 201
    custom_note = Notification.objects.filter(user=custom_member, kind="price_change").latest("id")
    assert "owner will update" in custom_note.message.lower()


@pytest.mark.django_db
def test_close_departed_members_via_run_daily(world):
    today = world["today"]
    row = world["member_row"]
    row.left_on = today - timedelta(days=1)
    row.status = MemberStatus.ACTIVE
    row.save(update_fields=["left_on", "status"])
    with (
        patch("jobs.services._try_advisory_lock", return_value=True),
        patch("jobs.services.billing_services.expire_fixed_term_plans", return_value=0),
        patch("jobs.services.billing_services.activate_ended_trials", return_value=0),
        patch("jobs.services.billing_services.generate_charges_for_all_plans", return_value={"plans": 0, "created": 0, "errors": 0}),
        patch("jobs.services.billing_services.lock_due_charges", return_value=0),
        patch("dues.services.ensure_dues", return_value=0),
    ):
        from jobs import services as job_services

        job_services.run_daily(today)
    row.refresh_from_db()
    assert row.status == MemberStatus.LEFT


@pytest.mark.django_db
def test_split_changed_sent_once(world):
    sends = []

    def capture(sender, **kwargs):
        sends.append(kwargs)

    with patch("core.signals.split_changed.send", side_effect=capture):
        client_for(world["owner"]).put(
            f"/api/shared-plans/{world['plan_x'].pk}/split/",
            {"split_type": "equal"},
            format="json",
        )
    assert len(sends) == 1


@pytest.mark.django_db
def test_notification_resolved_through_api(world, roomy_plan):
    owner = client_for(world["owner"])
    plan_id = roomy_plan
    member = world["member"]

    accept_email = "resolved-accept@example.com"
    accept_user = User.objects.create_user(email=accept_email, password=STRONG, name="RA", email_verified=True)
    a_id, a_token = _invite_token(owner, plan_id, accept_email)
    client_for(accept_user).get("/api/notifications/")  # materialize invite row
    assert _notif_resolved(accept_user, a_id) is None
    client_for(accept_user).post(f"/api/invites/{a_token}/accept/", {}, format="json")
    assert _notif_resolved(accept_user, a_id) == "joined"

    decline_email = "resolved-decline@example.com"
    decline_user = User.objects.create_user(email=decline_email, password=STRONG, name="RD", email_verified=True)
    d_id, d_token = _invite_token(owner, plan_id, decline_email)
    client_for(decline_user).get("/api/notifications/")
    client_for(decline_user).post(f"/api/invites/{d_token}/decline/", {}, format="json")
    assert _notif_resolved(decline_user, d_id) == "declined"

    cancel_email = "resolved-cancel@example.com"
    cancel_user = User.objects.create_user(email=cancel_email, password=STRONG, name="RC", email_verified=True)
    c_id, _ = _invite_token(owner, plan_id, cancel_email)
    client_for(cancel_user).get("/api/notifications/")
    owner.post(f"/api/invites/{c_id}/cancel/", {}, format="json")
    assert _notif_resolved(cancel_user, c_id) == "cancelled"


@pytest.mark.django_db
def test_notification_leave_resolved(world):
    owner = client_for(world["owner"])
    plan_id = world["plan_x"].pk
    mid = world["member_row"].pk
    client_for(world["member"]).post(f"/api/shared-plans/{plan_id}/leave-request/", {}, format="json")
    owner.get("/api/notifications/")
    assert _leave_notif_resolved(world["owner"], mid) is None
    owner.post(
        f"/api/members/{mid}/leave/",
        {"approve": False},
        format="json",
    )
    assert _leave_notif_resolved(world["owner"], mid) == "declined"

    client_for(world["member"]).post(f"/api/shared-plans/{plan_id}/leave-request/", {}, format="json")
    owner.post(
        f"/api/members/{mid}/leave/",
        {"approve": True, "leave_date": str(world["today"]), "unpaid": "keep"},
        format="json",
    )
    assert _leave_notif_resolved(world["owner"], mid) == "approved"
