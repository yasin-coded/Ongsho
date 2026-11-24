"""POST /api/me/close/ API."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from accounts import services as account_services
from accounts.cookies import REFRESH_COOKIE_NAME
from payments.models import Payment
from plans.models import Subscription
from sharing.models import Member, MemberStatus

from tests.test_account_closure import make_closable_owner
from tests.test_subscriptions import WORLD_PASS, assert_error_shape, client_for
from tests.test_transfers import ensure_owner_seat, start_transfer

User = get_user_model()
APP_HEADER = {"HTTP_X_REQUESTED_WITH": "Ongsho"}
CLOSE_PATH = "/api/me/close/"


def post_close(client, payload=None, **kwargs):
    body = payload if payload is not None else {"password": WORLD_PASS}
    return client.post(CLOSE_PATH, body, format="json", **kwargs)


def login_cookie(email, password=WORLD_PASS):
    client = APIClient()
    r = client.post("/api/auth/login/", {"email": email, "password": password}, format="json")
    assert r.status_code == 200, r.content
    return client, r.cookies[REFRESH_COOKIE_NAME].value


@pytest.mark.django_db
def test_close_anonymous_401():
    assert APIClient().post(CLOSE_PATH, {"password": WORLD_PASS}, format="json").status_code == 401


@pytest.mark.django_db
def test_close_get_method_not_allowed():
    user = User.objects.create_user(
        email="get-405@example.com", password=WORLD_PASS, name="G", email_verified=True
    )
    assert client_for(user).get(CLOSE_PATH).status_code == 405


@pytest.mark.django_db
def test_close_missing_password():
    r = client_for(User.objects.create_user(
        email="missing-pw@example.com", password=WORLD_PASS, name="M", email_verified=True
    )).post(CLOSE_PATH, {}, format="json")
    assert r.status_code == 400
    assert_error_shape(r)


@pytest.mark.django_db
def test_close_empty_password():
    user = User.objects.create_user(
        email="empty-pw@example.com", password=WORLD_PASS, name="E", email_verified=True
    )
    r = client_for(user).post(CLOSE_PATH, {"password": ""}, format="json")
    assert_error_shape(r)
    assert r.status_code == 400
    assert "password" in r.json()["error"]["fields"]


@pytest.mark.django_db
def test_close_wrong_password(world):
    user = world["outsider"]
    r = client_for(user).post(CLOSE_PATH, {"password": "not-it"}, format="json")
    assert_error_shape(r)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_password"
    user.refresh_from_db()
    assert user.is_active is True


@pytest.mark.django_db
def test_close_password_lockout(world):
    user = world["outsider"]
    client = client_for(user)
    for _ in range(5):
        bad = client.post(CLOSE_PATH, {"password": "bad-password"}, format="json")
        assert bad.status_code == 400
    locked = client.post(CLOSE_PATH, {"password": WORLD_PASS}, format="json")
    assert locked.status_code == 429
    assert locked.json()["error"]["code"] == "locked"


@pytest.mark.django_db
def test_close_staff_forbidden():
    user = User.objects.create_user(
        email="staff-close@example.com",
        password=WORLD_PASS,
        name="Staff",
        email_verified=True,
        is_staff=True,
    )
    r = post_close(client_for(user))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "staff_cannot_close"


@pytest.mark.django_db
def test_close_superuser_forbidden():
    user = User.objects.create_user(
        email="su-close@example.com",
        password=WORLD_PASS,
        name="SU",
        email_verified=True,
        is_superuser=True,
    )
    r = post_close(client_for(user))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "staff_cannot_close"


@pytest.mark.django_db
def test_close_owned_plans_blocker(world):
    r = post_close(client_for(world["owner"]))
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "owned_plans_remain"


@pytest.mark.django_db
def test_close_active_membership_blocker(world):
    user = User.objects.create_user(
        email="member-block@example.com", password=WORLD_PASS, name="Mem", email_verified=True
    )
    Member.objects.create(
        shared_plan=world["shared_x"],
        user=user,
        share_type=world["shared_x"].split_type,
        status=MemberStatus.ACTIVE,
        joined_on=world["plan_x"].start_date,
    )
    r = post_close(client_for(user))
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "active_membership"


@pytest.mark.django_db
def test_close_pending_transfer_blocker(world):
    ensure_owner_seat(world)
    Member.objects.filter(user=world["owner"], shared_plan=world["shared_y"]).update(
        status=MemberStatus.LEFT,
        left_on=world["today"],
    )
    Subscription.objects.filter(pk=world["plan_y"].pk).update(archived_on=timezone.now())
    target = User.objects.create_user(
        email="xfer-api@example.com", password=WORLD_PASS, name="T", email_verified=True
    )
    target_member = Member.objects.create(
        shared_plan=world["shared_x"],
        user=target,
        share_type=world["shared_x"].split_type,
        status=MemberStatus.ACTIVE,
        joined_on=world["plan_x"].start_date,
    )
    assert start_transfer(client_for(world["owner"]), world["plan_x"].pk, target_member.pk).status_code == 201
    r = post_close(client_for(world["owner"]))
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "pending_ownership_transfer"


@pytest.mark.django_db
def test_close_success(world):
    user = world["outsider"]
    original_email = user.email
    original_pk = user.pk
    login_r = APIClient().post(
        "/api/auth/login/",
        {"email": original_email, "password": WORLD_PASS},
        format="json",
    )
    refresh_before = login_r.cookies[REFRESH_COOKIE_NAME].value

    r = post_close(client_for(user))
    assert r.status_code == 204
    assert REFRESH_COOKIE_NAME in r.cookies
    assert r.cookies[REFRESH_COOKIE_NAME].value == ""

    user = User.objects.get(pk=original_pk)
    assert user.is_active is False
    assert user.email != original_email
    assert user.email.endswith(f"@{account_services.ACCOUNT_TOMBSTONE_DOMAIN}")

    refresh_after = APIClient().post(
        "/api/auth/refresh/",
        format="json",
        HTTP_COOKIE=f"{REFRESH_COOKIE_NAME}={refresh_before}",
        **APP_HEADER,
    )
    assert refresh_after.status_code == 401

    outstanding = OutstandingToken.objects.filter(user_id=original_pk)
    assert outstanding.exists()
    assert outstanding.count() == BlacklistedToken.objects.filter(token__in=outstanding).count()


@pytest.mark.django_db
def test_close_only_affects_authenticated_user(world):
    victim = world["outsider"]
    bystander = world["member"]
    victim_pk = victim.pk
    victim_email = victim.email
    r = post_close(client_for(bystander))
    assert r.status_code in (409, 403)  # member has active membership
    victim.refresh_from_db()
    assert victim.is_active is True
    assert victim.email == victim_email
    assert victim.pk == victim_pk


@pytest.mark.django_db
def test_close_body_user_id_ignored(world):
    user = world["outsider"]
    original_pk = user.pk
    r = client_for(user).post(
        CLOSE_PATH,
        {"password": WORLD_PASS, "user_id": world["owner"].pk},
        format="json",
    )
    assert r.status_code == 204
    assert User.objects.get(pk=original_pk).is_active is False
    assert User.objects.get(pk=world["owner"].pk).is_active is True


@pytest.mark.django_db
def test_post_close_login_and_register(world):
    user = world["outsider"]
    email = user.email
    post_close(client_for(user))
    assert (
        APIClient().post("/api/auth/login/", {"email": email, "password": WORLD_PASS}, format="json").status_code
        == 401
    )
    new_user = account_services.register_user(email=email, password=WORLD_PASS, name="Fresh")
    assert new_user.pk != user.pk
    assert new_user.is_active is True


@pytest.mark.django_db
def test_close_financial_history_intact(world):
    owner = make_closable_owner(world)
    original_pk = owner.pk
    payment_ids = list(Payment.objects.filter(recorded_by=owner).values_list("pk", flat=True))
    sub_id = world["plan_x"].pk
    r = post_close(client_for(owner))
    assert r.status_code == 204
    assert Subscription.all_with_archived.filter(pk=sub_id, owner_id=original_pk).exists()
    assert Payment.objects.filter(pk__in=payment_ids, recorded_by_id=original_pk).count() == len(payment_ids)


@pytest.mark.django_db
def test_delete_me_profile_still_405(world):
    assert client_for(world["outsider"]).delete("/api/me/").status_code == 405


@pytest.mark.django_db
def test_profile_and_password_unaffected_for_other_user(world):
    user = world["outsider"]
    client = client_for(user)
    assert client.get("/api/me/").status_code == 200
    assert client.patch("/api/me/", {"name": "Still Here"}, format="json").status_code == 200
    other = User.objects.create_user(
        email="pw-other@example.com", password=WORLD_PASS, name="Other", email_verified=True
    )
    other_client = client_for(other)
    assert other_client.post(
        "/api/me/password/",
        {"current_password": WORLD_PASS, "new_password": "NewPass12345"},
        format="json",
    ).status_code == 200


@pytest.mark.django_db
def test_logout_still_works(world):
    client, _ = login_cookie(world["outsider"].email)
    assert client.post("/api/auth/logout/", **APP_HEADER).status_code == 204


@pytest.mark.django_db
def test_stale_access_jwt_rejected_after_close(world):
    user = world["outsider"]
    login_r = APIClient().post(
        "/api/auth/login/",
        {"email": user.email, "password": WORLD_PASS},
        format="json",
    )
    assert login_r.status_code == 200
    access = login_r.json()["access"]
    assert post_close(client_for(user)).status_code == 204

    protected = APIClient().get(
        "/api/me/",
        HTTP_AUTHORIZATION=f"Bearer {access}",
        **APP_HEADER,
    )
    assert protected.status_code == 401
    assert_error_shape(protected)
    assert protected.json()["error"]["code"] in ("token_not_valid", "user_inactive", "invalid_token")