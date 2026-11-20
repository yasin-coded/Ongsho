import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.models import Category, ServiceName
from plans.models import Subscription

User = get_user_model()
STRONG = "HorseBatteryStaple99"


@pytest.fixture
def user_a(db):
    return User.objects.create_user(email="a@example.com", password=STRONG, name="A", email_verified=True)


@pytest.fixture
def user_b(db):
    return User.objects.create_user(email="b@example.com", password=STRONG, name="B", email_verified=True)


def assert_error_shape(response):
    assert response.status_code >= 400
    body = response.json()
    assert set(body.keys()) == {"error"}
    err = body["error"]
    assert set(err.keys()) == {"code", "message", "fields"}


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


DELETE_ANON = [
    "/api/categories/1/",
    "/api/service-names/1/",
]


@pytest.mark.django_db
@pytest.mark.parametrize("path", DELETE_ANON)
def test_delete_detail_anonymous_401(path):
    response = APIClient().delete(path)
    assert response.status_code == 401
    assert_error_shape(response)


@pytest.mark.django_db
class TestCatalogInUse:
    def test_in_use_when_non_archived_plan_uses_row(self, user_a):
        client = client_for(user_a)
        custom = client.post("/api/categories/", {"name": "Used Cat"}, format="json").json()
        cat_id = custom["id"]
        streaming = Category.objects.get(is_preset=True, name="Streaming")
        sn = client.post(
            "/api/service-names/",
            {"name": "Used SN", "category": cat_id},
            format="json",
        ).json()
        sn_id = sn["id"]
        sub = Subscription.objects.filter(owner=user_a).first()
        if sub is None:
            from core.choices import Currency, PaymentMethod
            from core.dates import today_dhaka
            from plans.models import CycleUnit, PlanMode, RenewalType, SubscriptionStatus

            sub = Subscription.objects.create(
                owner=user_a,
                service_name_id=sn_id,
                category_id=cat_id,
                plan_name="Solo",
                plan_mode=PlanMode.OWNER,
                currency=Currency.BDT,
                cycle_unit=CycleUnit.MONTH,
                cycle_count=1,
                anchor_day=1,
                start_date="2026-01-01",
                renewal_type=RenewalType.AUTO,
                status=SubscriptionStatus.ACTIVE,
                recommended_method=PaymentMethod.BKASH,
                billing_from=today_dhaka(),
            )
        else:
            Subscription.objects.filter(pk=sub.pk).update(category_id=cat_id, service_name_id=sn_id)

        cats = {c["id"]: c for c in client.get("/api/categories/").json()}
        names = {n["id"]: n for n in client.get("/api/service-names/").json()}
        assert cats[cat_id]["in_use"] is True
        assert names[sn_id]["in_use"] is True
        assert cats[streaming.id]["in_use"] is False

    def test_in_use_false_when_only_archived_plan(self, user_a):
        client = client_for(user_a)
        custom = client.post("/api/categories/", {"name": "Archived Only"}, format="json").json()
        cat_id = custom["id"]
        from core.choices import Currency, PaymentMethod
        from core.dates import today_dhaka
        from plans.models import CycleUnit, PlanMode, RenewalType, SubscriptionStatus

        sub = Subscription.objects.create(
            owner=user_a,
            service_name=ServiceName.objects.filter(is_preset=True).first(),
            category_id=cat_id,
            plan_name="Archived",
            plan_mode=PlanMode.OWNER,
            currency=Currency.BDT,
            cycle_unit=CycleUnit.MONTH,
            cycle_count=1,
            anchor_day=1,
            start_date="2026-01-01",
            renewal_type=RenewalType.AUTO,
            status=SubscriptionStatus.ACTIVE,
            recommended_method=PaymentMethod.BKASH,
            billing_from=today_dhaka(),
            archived_on=timezone.now(),
        )
        assert sub.pk
        cats = {c["id"]: c for c in client.get("/api/categories/").json()}
        assert cats[cat_id]["in_use"] is False


@pytest.mark.django_db
class TestDeleteCategory:
    def test_preset_forbidden(self, user_a):
        preset = Category.objects.filter(is_preset=True).first()
        response = client_for(user_a).delete(f"/api/categories/{preset.id}/")
        assert response.status_code == 403
        assert_error_shape(response)
        assert response.json()["error"]["code"] == "preset_not_deletable"

    def test_other_users_custom_not_found(self, user_a, user_b):
        cat_id = (
            client_for(user_a).post("/api/categories/", {"name": "Private"}, format="json").json()["id"]
        )
        response = client_for(user_b).delete(f"/api/categories/{cat_id}/")
        assert response.status_code == 404
        assert_error_shape(response)

    def test_deletes_and_moves_plans_to_other(self, user_a):
        client = client_for(user_a)
        cat_id = client.post("/api/categories/", {"name": "Gone Cat"}, format="json").json()["id"]
        other = Category.objects.get(is_preset=True, name="Other")
        sn = ServiceName.objects.filter(is_preset=True).first()
        from core.choices import Currency, PaymentMethod
        from core.dates import today_dhaka
        from plans.models import CycleUnit, PlanMode, RenewalType, SubscriptionStatus

        sub = Subscription.objects.create(
            owner=user_a,
            service_name=sn,
            category_id=cat_id,
            plan_name="On Cat",
            plan_mode=PlanMode.OWNER,
            currency=Currency.BDT,
            cycle_unit=CycleUnit.MONTH,
            cycle_count=1,
            anchor_day=2,
            start_date="2026-02-02",
            renewal_type=RenewalType.AUTO,
            status=SubscriptionStatus.ACTIVE,
            recommended_method=PaymentMethod.BKASH,
            billing_from=today_dhaka(),
        )
        response = client.delete(f"/api/categories/{cat_id}/")
        assert response.status_code == 204
        assert not Category.objects.filter(pk=cat_id).exists()
        sub.refresh_from_db()
        assert sub.category_id == other.id

    def test_detail_get_returns_405(self, user_a):
        cat_id = client_for(user_a).post("/api/categories/", {"name": "X"}, format="json").json()["id"]
        response = client_for(user_a).get(f"/api/categories/{cat_id}/")
        assert response.status_code == 405
        assert_error_shape(response)


@pytest.mark.django_db
class TestDeleteServiceName:
    def test_preset_forbidden(self, user_a):
        preset = ServiceName.objects.filter(is_preset=True).first()
        response = client_for(user_a).delete(f"/api/service-names/{preset.id}/")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "preset_not_deletable"

    def test_other_users_not_found(self, user_a, user_b):
        ca = client_for(user_a)
        cat_id = ca.post("/api/categories/", {"name": "SN Cat"}, format="json").json()["id"]
        sn_id = ca.post(
            "/api/service-names/", {"name": "SN Private", "category": cat_id}, format="json"
        ).json()["id"]
        response = client_for(user_b).delete(f"/api/service-names/{sn_id}/")
        assert response.status_code == 404

    def test_in_use_conflict_includes_archived(self, user_a):
        client = client_for(user_a)
        cat_id = client.post("/api/categories/", {"name": "SN Hold"}, format="json").json()["id"]
        sn_id = client.post(
            "/api/service-names/", {"name": "SN Hold Name", "category": cat_id}, format="json"
        ).json()["id"]
        from core.choices import Currency, PaymentMethod
        from core.dates import today_dhaka
        from plans.models import CycleUnit, PlanMode, RenewalType, SubscriptionStatus

        Subscription.all_with_archived.create(
            owner=user_a,
            service_name_id=sn_id,
            category_id=cat_id,
            plan_name="Archived SN",
            plan_mode=PlanMode.OWNER,
            currency=Currency.BDT,
            cycle_unit=CycleUnit.MONTH,
            cycle_count=1,
            anchor_day=3,
            start_date="2026-03-03",
            renewal_type=RenewalType.AUTO,
            status=SubscriptionStatus.ACTIVE,
            recommended_method=PaymentMethod.BKASH,
            billing_from=today_dhaka(),
            archived_on=timezone.now(),
        )
        response = client.delete(f"/api/service-names/{sn_id}/")
        assert response.status_code == 409
        assert_error_shape(response)
        assert response.json()["error"]["code"] == "in_use"
        assert ServiceName.objects.filter(pk=sn_id).exists()

    def test_unused_deletes_204(self, user_a):
        client = client_for(user_a)
        cat_id = client.post("/api/categories/", {"name": "SN Free"}, format="json").json()["id"]
        sn_id = client.post(
            "/api/service-names/", {"name": "Orphan SN", "category": cat_id}, format="json"
        ).json()["id"]
        response = client.delete(f"/api/service-names/{sn_id}/")
        assert response.status_code == 204
        assert not ServiceName.objects.filter(pk=sn_id).exists()
