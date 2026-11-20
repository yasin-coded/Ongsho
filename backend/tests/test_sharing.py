import hashlib

import pytest
from django.core import mail
from rest_framework.test import APIClient

from sharing.models import Invite, Member, SharedPlan

from tests.outbox_helpers import flush_outbound_to_mailbox
from tests.test_subscriptions import assert_error_shape, client_for, plan_payload

STRONG = "pass12345"


@pytest.mark.django_db
class TestSharePlan:
    def test_owner_share_creates_owner_seat(self, world):
        client = client_for(world["owner"])
        created = client.post("/api/subscriptions/", plan_payload(plan_name="Share Me"), format="json")
        sub_id = created.json()["id"]
        r = client.post(
            f"/api/subscriptions/{sub_id}/share/",
            {"split_type": "equal", "seats": 2},
            format="json",
        )
        assert r.status_code == 201
        shared = SharedPlan.objects.get(subscription_id=sub_id)
        assert Member.objects.filter(shared_plan=shared, user=world["owner"]).exists()

    def test_already_shared_409(self, world):
        r = client_for(world["owner"]).post(
            f"/api/subscriptions/{world['plan_x'].pk}/share/",
            {"split_type": "equal", "seats": 3},
            format="json",
        )
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "already_shared"

    def test_composite_create_rolls_back(self, world):
        client = client_for(world["owner"])
        before = SharedPlan.objects.count()
        r = client.post(
            "/api/subscriptions/",
            {**plan_payload(plan_name="Bad Invites"), "seats": 2, "invite_emails": ["not-an-email"]},
            format="json",
        )
        assert r.status_code == 400
        assert SharedPlan.objects.count() == before


@pytest.mark.django_db
class TestInvites:
    @pytest.fixture(autouse=True)
    def mail_backend(self, settings):
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

    def test_create_invite_hashes_token(self, world):
        mail.outbox.clear()
        r = client_for(world["owner"]).post(
            f"/api/shared-plans/{world['plan_x'].pk}/invites/",
            {"email": "newinv@example.com"},
            format="json",
        )
        assert r.status_code == 201
        assert "link" in r.json()
        flush_outbound_to_mailbox()
        invite = Invite.objects.get(email="newinv@example.com")
        assert len(invite.token_hash) == 64
        assert invite.token_hash == hashlib.sha256(r.json()["link"].split("/")[-1].encode()).hexdigest()
        assert len(mail.outbox) == 1

    def test_public_get_404(self):
        assert APIClient().get("/api/invites/bad-token/").status_code == 404

    def test_wrong_email_service_raises(self, world):
        from core.dates import today_dhaka
        from core.exceptions import Forbidden
        from sharing import services

        created = client_for(world["owner"]).post(
            f"/api/shared-plans/{world['plan_x'].pk}/invites/",
            {"email": "svc-accept@example.com"},
            format="json",
        )
        token = created.json()["link"].split("/")[-1]
        with pytest.raises(Forbidden):
            services.accept_invite(world["outsider"], token=token, today=today_dhaka())

    def test_wrong_email_accept_403(self, world):
        created = client_for(world["owner"]).post(
            f"/api/shared-plans/{world['plan_x'].pk}/invites/",
            {"email": "accept@example.com"},
            format="json",
        )
        token = created.json()["link"].split("/")[-1]
        other = world["outsider"]
        r = client_for(other).post(f"/api/invites/{token}/accept/", {}, format="json")
        assert r.status_code == 403, r.content


@pytest.mark.django_db
def test_shared_plan_scoping_404(world):
    assert client_for(world["outsider"]).get(f"/api/shared-plans/{world['plan_x'].pk}/").status_code == 404


@pytest.mark.django_db
def test_anonymous_401():
    assert APIClient().get("/api/shared-plans/1/").status_code == 401
    assert_error_shape(APIClient().get("/api/shared-plans/1/"))
