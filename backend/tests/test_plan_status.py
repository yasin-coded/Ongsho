from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditLog
from catalog.models import Category, ServiceName
from core.choices import Currency, PaymentMethod
from core.dates import today_dhaka

from django.utils import timezone
from plans.models import CycleUnit, PlanMode, RenewalType, Subscription, SubscriptionStatus

STATUS_PATHS = [
    "pause",
    "resume",
    "cancel",
    "renew",
]


def assert_error_shape(response):
    assert response.status_code >= 400
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "fields"}


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def make_subscription(owner, *, status, renewal_type=RenewalType.AUTO, end_date=None, trial_end_date=None):
    streaming = Category.objects.get(is_preset=True, name="Streaming")
    netflix = ServiceName.objects.filter(is_preset=True, name="Netflix", category=streaming).first()
    return Subscription.objects.create(
        owner=owner,
        service_name=netflix,
        category=streaming,
        plan_name="Status Plan",
        plan_mode=PlanMode.OWNER,
        currency=Currency.BDT,
        cycle_unit=CycleUnit.MONTH,
        cycle_count=1,
        anchor_day=5,
        start_date="2020-01-05",
        trial_end_date=trial_end_date,
        renewal_type=renewal_type,
        end_date=end_date,
        status=status,
        recommended_method=PaymentMethod.BKASH,
        billing_from=today_dhaka(),
    )


def post_status(client, sub_id, action, body=None):
    url = f"/api/subscriptions/{sub_id}/{action}/"
    if body is None:
        return client.post(url, format="json")
    return client.post(url, body, format="json")


@pytest.mark.django_db
@pytest.mark.parametrize("action", STATUS_PATHS)
def test_anonymous_401(action):
    response = post_status(APIClient(), 1, action)
    assert response.status_code == 401
    assert_error_shape(response)


@pytest.mark.django_db
@pytest.mark.parametrize("action", STATUS_PATHS)
def test_get_405(world, action):
    sub = make_subscription(world["owner"], status=SubscriptionStatus.ACTIVE)
    response = client_for(world["owner"]).get(f"/api/subscriptions/{sub.pk}/{action}/")
    assert response.status_code == 405
    assert_error_shape(response)


@pytest.mark.django_db
class TestAllowedMoves:
    def test_pause_trial_and_active(self, world):
        client = client_for(world["owner"])
        for status in (SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE):
            sub = make_subscription(world["owner"], status=status)
            before = AuditLog.objects.count()
            response = post_status(client, sub.pk, "pause")
            assert response.status_code == 200
            assert response.json()["status"] == SubscriptionStatus.PAUSED
            sub.refresh_from_db()
            assert sub.status == SubscriptionStatus.PAUSED
            assert AuditLog.objects.filter(action="plan.paused", entity_id=sub.pk).count() == 1
            assert AuditLog.objects.count() == before + 1

    def test_resume_to_trial_or_active(self, world):
        client = client_for(world["owner"])
        trial_end = today_dhaka() + timedelta(days=10)
        sub_trial = make_subscription(
            world["owner"],
            status=SubscriptionStatus.PAUSED,
            trial_end_date=trial_end,
        )
        assert post_status(client, sub_trial.pk, "resume").json()["status"] == SubscriptionStatus.TRIAL

        sub_active = make_subscription(world["owner"], status=SubscriptionStatus.PAUSED, trial_end_date=None)
        assert post_status(client, sub_active.pk, "resume").json()["status"] == SubscriptionStatus.ACTIVE

        past_trial = make_subscription(
            world["owner"],
            status=SubscriptionStatus.PAUSED,
            trial_end_date=today_dhaka() - timedelta(days=1),
        )
        assert post_status(client, past_trial.pk, "resume").json()["status"] == SubscriptionStatus.ACTIVE

    def test_cancel_sources(self, world):
        client = client_for(world["owner"])
        for status in (SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE, SubscriptionStatus.PAUSED):
            sub = make_subscription(world["owner"], status=status)
            response = post_status(client, sub.pk, "cancel")
            assert response.status_code == 200
            assert response.json()["status"] == SubscriptionStatus.CANCELLED

    def test_renew_fixed_term(self, world):
        client = client_for(world["owner"])
        today = today_dhaka()
        current_end = today + timedelta(days=30)
        sub = make_subscription(
            world["owner"],
            status=SubscriptionStatus.EXPIRED,
            renewal_type=RenewalType.FIXED_TERM,
            end_date=current_end - timedelta(days=5),
        )
        new_end = current_end + timedelta(days=60)
        response = post_status(client, sub.pk, "renew", {"end_date": str(new_end)})
        assert response.status_code == 200
        assert response.json()["status"] == SubscriptionStatus.ACTIVE
        assert response.json()["end_date"] == str(new_end)
        row = AuditLog.objects.get(entity_id=sub.pk, action="plan.renewed")
        assert row.old_value["status"] == SubscriptionStatus.EXPIRED
        assert row.new_value["end_date"] == str(new_end)


@pytest.mark.django_db
class TestDisallowedMoves:
    def test_invalid_status_change_unchanged(self, world):
        client = client_for(world["owner"])
        cases = [
            (SubscriptionStatus.PAUSED, "pause"),
            (SubscriptionStatus.CANCELLED, "pause"),
            (SubscriptionStatus.ACTIVE, "resume"),
            (SubscriptionStatus.CANCELLED, "cancel"),
            (SubscriptionStatus.EXPIRED, "cancel"),
            (SubscriptionStatus.CANCELLED, "renew"),
        ]
        for status, action in cases:
            sub = make_subscription(
                world["owner"],
                status=status,
                renewal_type=RenewalType.FIXED_TERM,
                end_date=today_dhaka() + timedelta(days=30),
            )
            before = sub.status
            if action == "renew":
                body = {"end_date": str(today_dhaka() + timedelta(days=90))}
            else:
                body = None
            response = post_status(client, sub.pk, action, body)
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "invalid_status_change"
            sub.refresh_from_db()
            assert sub.status == before
            assert AuditLog.objects.filter(entity_id=sub.pk).count() == 0

    def test_renew_validation(self, world):
        client = client_for(world["owner"])
        auto = make_subscription(world["owner"], status=SubscriptionStatus.ACTIVE)
        assert post_status(client, auto.pk, "renew", {"end_date": "2099-01-01"}).json()["error"]["code"] == "not_fixed_term"

        fixed = make_subscription(
            world["owner"],
            status=SubscriptionStatus.ACTIVE,
            renewal_type=RenewalType.FIXED_TERM,
            end_date=today_dhaka() + timedelta(days=30),
        )
        past = post_status(client, fixed.pk, "renew", {"end_date": str(today_dhaka() - timedelta(days=1))})
        assert_error_shape(past)
        assert past.status_code == 400
        assert "end_date" in past.json()["error"]["fields"]

        not_extended = post_status(
            client,
            fixed.pk,
            "renew",
            {"end_date": str(today_dhaka() + timedelta(days=30))},
        )
        assert_error_shape(not_extended)
        assert not_extended.status_code == 400


@pytest.mark.django_db
class TestAccessControl:
    def test_other_user_and_archived_404(self, world):
        sub = world["plan_x"]
        archived = make_subscription(world["owner"], status=SubscriptionStatus.ACTIVE)
        Subscription.all_with_archived.filter(pk=archived.pk).update(archived_on=timezone.now())
        outsider = client_for(world["outsider"])
        owner = client_for(world["owner"])
        for action in STATUS_PATHS:
            body = {"end_date": "2099-01-01"} if action == "renew" else None
            assert post_status(outsider, sub.pk, action, body).status_code == 404
            assert post_status(owner, archived.pk, action, body).status_code == 404
