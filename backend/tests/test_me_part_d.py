from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from core.choices import PaymentMethod
from notifications.models import Notification
from payments.models import Payment, ReviewStatus
from plans.models import Subscription
from tests.outbox_helpers import flush_outbound_to_mailbox

User = get_user_model()
STRONG = "HorseBatteryStaple99"

@pytest.fixture(autouse=True)
def profile_env(settings):
    settings.FRONTEND_BASE_URL = "http://localhost:5173"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "noreply@example.com"


NEW_ENDPOINTS = [
    ("/api/me/email/resend/", "post"),
    ("/api/me/nav-counts/", "get"),
    ("/api/reminders/settings/", "get"),
    ("/api/reminders/settings/", "patch"),
]


def assert_error_shape(response):
    assert response.status_code >= 400
    data = response.json()
    assert set(data) == {"error"}
    assert set(data["error"]) == {"code", "message", "fields"}


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def request_email_change(client, new_email, password=STRONG):
    response = client.post(
        "/api/me/email/",
        {"new_email": new_email, "password": password},
        format="json",
    )
    if response.status_code == 200:
        flush_outbound_to_mailbox()
    return response


@pytest.mark.django_db
@pytest.mark.parametrize("path,method", NEW_ENDPOINTS)
def test_new_endpoints_anonymous_401(path, method):
    client = APIClient()
    call = getattr(client, method)
    if method == "patch":
        response = call(path, {"email": False}, format="json")
    elif method == "post":
        response = call(path, {}, format="json")
    else:
        response = call(path)
    assert response.status_code == 401
    assert_error_shape(response)


@pytest.mark.django_db
class TestProfilePlanCounts:
    def test_plans_owned_and_joined(self, world):
        owner_client = client_for(world["owner"])
        member_client = client_for(world["member"])
        outsider_client = client_for(world["outsider"])

        owner_me = owner_client.get("/api/me/").json()
        member_me = member_client.get("/api/me/").json()
        assert owner_me["plans_owned"] == 1
        assert owner_me["plans_joined"] == 1
        assert member_me["plans_owned"] == 1
        assert member_me["plans_joined"] == 1
        assert outsider_client.get("/api/me/").json()["plans_owned"] == 0
        assert outsider_client.get("/api/me/").json()["plans_joined"] == 0

    def test_archived_excluded_from_counts(self, world):
        Subscription.objects.filter(pk=world["plan_x"].pk).update(archived_on=timezone.now())
        data = client_for(world["owner"]).get("/api/me/").json()
        assert data["plans_owned"] == 0


@pytest.mark.django_db
class TestEmailChangeResend:
    def test_nothing_pending(self):
        user = User.objects.create_user(
            email="nore@example.com", password=STRONG, name="N", email_verified=True
        )
        response = client_for(user).post("/api/me/email/resend/", {}, format="json")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "nothing_pending"

    def test_resend_and_cooldown(self):
        user = User.objects.create_user(
            email="res@example.com", password=STRONG, name="R", email_verified=True
        )
        client = client_for(user)
        mail.outbox.clear()
        request_email_change(client, "res-new@example.com")
        assert len(mail.outbox) == 1
        mail.outbox.clear()
        user.refresh_from_db()
        client.force_authenticate(user=user)
        first = client.post("/api/me/email/resend/", {}, format="json")
        assert first.status_code == 200
        flush_outbound_to_mailbox()
        assert len(mail.outbox) == 1
        body = first.json()
        mail.outbox.clear()
        second = client.post("/api/me/email/resend/", {}, format="json")
        assert second.status_code == 200
        assert second.json() == body
        assert len(mail.outbox) == 0


@pytest.mark.django_db
class TestNavCounts:
    def test_counts_and_scoping(self, world):
        owner = world["owner"]
        member = world["member"]
        outsider = world["outsider"]
        shared_x = world["shared_x"]
        member_row = shared_x.members.get(user=member)

        Payment.objects.create(
            shared_plan=shared_x,
            member=member_row,
            recorded_by=member,
            method=PaymentMethod.BKASH,
            amount=Decimal("100.00"),
            review_status=ReviewStatus.PENDING,
        )
        Notification.objects.create(user=owner, kind="test", message="Hi", read_at=None)
        Notification.objects.create(user=owner, kind="test", message="Read", read_at=timezone.now())
        Notification.objects.create(user=outsider, kind="test", message="Other", read_at=None)

        owner_counts = client_for(owner).get("/api/me/nav-counts/").json()
        assert owner_counts == {"reviews": 1, "dues": 0, "unread": 1}

        member_counts = client_for(member).get("/api/me/nav-counts/").json()
        assert member_counts["reviews"] == 0
        assert member_counts["dues"] == 1
        assert member_counts["unread"] == 0


@pytest.mark.django_db
class TestReminderSettings:
    def test_unknown_field_not_editable(self):
        user = User.objects.create_user(
            email="rem3@example.com", password=STRONG, name="Rem3", email_verified=True
        )
        response = client_for(user).patch("/api/reminders/settings/", {"name": "hack"}, format="json")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "field_not_editable"
        assert "name" in response.json()["error"]["fields"]
