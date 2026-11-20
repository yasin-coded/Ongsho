from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from datetime import date, timedelta


from audit.models import AuditLog
from billing.models import Charge
from dues.models import Due
from catalog.models import Category, ServiceName
from core.choices import PaymentMethod
from core.dates import today_dhaka
from payments.models import Payment, ReviewStatus
from plans.models import ExchangeRate, PriceChange, Subscription
from sharing.models import Member, MemberStatus, SharedPlan, SplitType

User = get_user_model()
WORLD_PASS = "pass12345"

ENDPOINTS = [
    "/api/subscriptions/",
    "/api/subscriptions/1/",
    "/api/subscriptions/1/price-changes/",
]


def assert_error_shape(response):
    assert response.status_code >= 400
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "fields"}


def client_for(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def audit_count():
    return AuditLog.objects.count()


def make_payment(shared, member, recorded_by, review_status):
    return Payment.objects.create(
        shared_plan=shared,
        member=member,
        recorded_by=recorded_by,
        method=PaymentMethod.BKASH,
        amount=Decimal("50.00"),
        review_status=review_status,
    )


def plan_payload(**overrides):
    streaming = Category.objects.get(is_preset=True, name="Streaming")
    netflix = ServiceName.objects.filter(is_preset=True, name="Netflix", category=streaming).first()
    data = {
        "service_name": netflix.id,
        "plan_name": "Test Plan",
        "plan_mode": "owner",
        "currency": "BDT",
        "amount": "100.00",
        "cycle_unit": "month",
        "cycle_count": 1,
        "start_date": "2026-02-05",
        "renewal_type": "auto",
        "recommended_method": "bkash",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
@pytest.mark.parametrize("path", ENDPOINTS)
def test_anonymous_401(path):
    r = APIClient().get(path)
    assert r.status_code == 401
    assert_error_shape(r)


@pytest.mark.django_db
def test_put_detail_405(world):
    sub = world["plan_x"]
    r = client_for(world["owner"]).put(f"/api/subscriptions/{sub.pk}/", {}, format="json")
    assert r.status_code == 405
    assert_error_shape(r)


@pytest.mark.django_db
class TestCreate:
    def test_bdt_create(self, world):
        client = client_for(world["owner"])
        r = client.post("/api/subscriptions/", plan_payload(), format="json")
        assert r.status_code == 201
        body = r.json()
        assert body["anchor_day"] == 5
        assert body["amount"] == "100.00"
        sub = Subscription.objects.get(pk=body["id"])
        assert sub.owner_id == world["owner"].id
        assert PriceChange.objects.filter(subscription=sub, effective_from="2026-02-05").exists()
        assert AuditLog.objects.filter(action="plan.created", entity_id=sub.pk).count() == 1

    def test_usd_preview_and_rate(self, world):
        client = client_for(world["owner"])
        r = client.post(
            "/api/subscriptions/",
            plan_payload(currency="USD", amount="5.99", exchange_rate="122.5"),
            format="json",
        )
        assert r.status_code == 201
        assert r.json()["amount_bdt_preview"] == "733.78"
        assert ExchangeRate.objects.filter(user=world["owner"], usd_to_bdt=Decimal("122.5000")).exists()

    def test_bdt_rejects_exchange_rate(self, world):
        r = client_for(world["owner"]).post(
            "/api/subscriptions/",
            plan_payload(exchange_rate="120"),
            format="json",
        )
        assert r.status_code == 400
        assert "exchange_rate" in r.json()["error"]["fields"]

    def test_trial_status(self, world):
        today = today_dhaka().isoformat()
        tomorrow = (today_dhaka() + timedelta(days=1)).isoformat()
        r = client_for(world["owner"]).post(
            "/api/subscriptions/",
            plan_payload(start_date=today, trial_end_date=tomorrow),
            format="json",
        )
        assert r.status_code == 201
        assert r.json()["status"] == "trial"

    def test_ignores_client_owner_fields(self, world):
        r = client_for(world["owner"]).post(
            "/api/subscriptions/",
            plan_payload(owner=999, status="cancelled", anchor_day=1),
            format="json",
        )
        assert r.status_code == 201
        assert r.json()["status"] == "active"
        assert r.json()["anchor_day"] == 5


@pytest.mark.django_db
class TestValidation:
    def test_cases(self, world):
        client = client_for(world["owner"])
        cases = [
            plan_payload(renewal_type="fixed_term"),
            plan_payload(renewal_type="fixed_term", end_date="2026-02-04", start_date="2026-02-05"),
            plan_payload(renewal_type="auto", end_date="2026-12-01"),
            plan_payload(start_date="2026-02-05", trial_end_date="2026-02-01"),
            plan_payload(cycle_count=0),
            plan_payload(cycle_unit="bad"),
            plan_payload(amount="0"),
            plan_payload(amount="-1"),
            plan_payload(amount="1.234"),
            plan_payload(plan_name=""),
            plan_payload(plan_name="x" * 256),
            {**plan_payload(), "plan_mode": None, "recommended_method": None},
        ]
        for payload in cases:
            if "plan_mode" in payload and payload["plan_mode"] is None:
                payload.pop("plan_mode")
                payload.pop("recommended_method", None)
                r = client.post("/api/subscriptions/", payload, format="json")
            else:
                r = client.post("/api/subscriptions/", payload, format="json")
            assert r.status_code == 400, payload


@pytest.mark.django_db
class TestScoping:
    def test_other_user_404(self, world):
        sub = world["plan_x"]
        c = client_for(world["outsider"])
        assert c.get(f"/api/subscriptions/{sub.pk}/").status_code == 404
        assert c.patch(f"/api/subscriptions/{sub.pk}/", {"plan_name": "X"}, format="json").status_code == 404
        assert (
            c.delete(f"/api/subscriptions/{sub.pk}/", {"password": WORLD_PASS}, format="json").status_code == 404
        )
        assert c.get(f"/api/subscriptions/{sub.pk}/price-changes/").status_code == 404

    def test_list_only_own(self, world):
        owner_client = client_for(world["owner"])
        member_client = client_for(world["member"])
        ids_o = {p["id"] for p in owner_client.get("/api/subscriptions/").json()["results"]}
        ids_m = {p["id"] for p in member_client.get("/api/subscriptions/").json()["results"]}
        assert world["plan_x"].pk in ids_o
        assert world["plan_y"].pk not in ids_o
        assert world["plan_y"].pk in ids_m

    def test_archived_hidden(self, world):
        sub = world["plan_x"]
        Subscription.all_with_archived.filter(pk=sub.pk).update(archived_on=timezone.now())
        assert client_for(world["owner"]).get(f"/api/subscriptions/{sub.pk}/").status_code == 404
        assert sub.pk not in {p["id"] for p in client_for(world["owner"]).get("/api/subscriptions/").json()["results"]}


@pytest.mark.django_db
class TestPatchDeletePrice:
    def test_plan_mode_locked(self, world):
        sub = world["plan_x"]
        r = client_for(world["owner"]).patch(
            f"/api/subscriptions/{sub.pk}/", {"plan_mode": "reseller"}, format="json"
        )
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "plan_mode_locked"
        sub.refresh_from_db()
        assert sub.plan_mode == "owner"

    def test_field_not_editable(self, world):
        sub = world["plan_x"]
        r = client_for(world["owner"]).patch(f"/api/subscriptions/{sub.pk}/", {"amount": "9.99"}, format="json")
        assert r.json()["error"]["code"] == "field_not_editable"

    def test_editable_fields(self, world):
        sub = world["plan_x"]
        r = client_for(world["owner"]).patch(
            f"/api/subscriptions/{sub.pk}/",
            {"plan_name": " Renamed ", "note": "note", "rarely_used": True},
            format="json",
        )
        assert r.status_code == 200
        sub.refresh_from_db()
        assert sub.plan_name == "Renamed"
        assert AuditLog.objects.filter(action="plan.updated", entity_id=sub.pk).exists()

    def test_delete_password(self, world):
        sub = world["plan_x"]
        c = client_for(world["owner"])
        assert c.delete(f"/api/subscriptions/{sub.pk}/", {}, format="json").status_code == 400
        assert (
            c.delete(f"/api/subscriptions/{sub.pk}/", {"password": "wrong"}, format="json").status_code == 400
        )
        assert c.delete(f"/api/subscriptions/{sub.pk}/", {"password": WORLD_PASS}, format="json").status_code == 204
        assert not Subscription.objects.filter(pk=sub.pk).exists()

    def test_price_changes(self, world):
        sub = world["plan_x"]
        c = client_for(world["owner"])
        listed = c.get(f"/api/subscriptions/{sub.pk}/price-changes/").json()
        assert len(listed) == 1
        eff = str(today_dhaka() + timedelta(days=10))
        create = c.post(
            f"/api/subscriptions/{sub.pk}/price-changes/",
            {"amount": "110.00", "effective_from": eff},
            format="json",
        )
        assert create.status_code == 201
        dup = c.post(
            f"/api/subscriptions/{sub.pk}/price-changes/",
            {"amount": "120.00", "effective_from": eff},
            format="json",
        )
        assert dup.status_code == 200
        assert PriceChange.objects.filter(subscription=sub, effective_from=eff).get().amount == Decimal("120.00")
        assert AuditLog.objects.filter(action="price_change.created", entity_id__isnull=False).count() == 2


@pytest.mark.django_db
class TestDeleteArchive:
    def test_no_shared_plan_hard_delete(self, world):
        client = client_for(world["owner"])
        created = client.post("/api/subscriptions/", plan_payload(plan_name="Solo Plan"), format="json")
        sub_id = created.json()["id"]
        before = audit_count()
        assert client.delete(f"/api/subscriptions/{sub_id}/", {"password": WORLD_PASS}, format="json").status_code == 204
        assert not Subscription.all_with_archived.filter(pk=sub_id).exists()
        assert audit_count() == before + 1
        assert AuditLog.objects.filter(action="plan.deleted", entity_id=sub_id).count() == 1

    def test_pending_or_rejected_still_hard_delete(self, world):
        sub = world["plan_y"]
        member = Member.objects.get(shared_plan=world["shared_y"], user=world["owner"])
        make_payment(world["shared_y"], member, world["member"], ReviewStatus.PENDING)
        make_payment(world["shared_y"], member, world["member"], ReviewStatus.REJECTED)
        c = client_for(world["member"])
        sub_id = sub.pk
        assert c.delete(f"/api/subscriptions/{sub_id}/", {"password": WORLD_PASS}, format="json").status_code == 204
        assert not Subscription.all_with_archived.filter(pk=sub_id).exists()
        assert not Payment.objects.filter(shared_plan_id=world["shared_y"].pk).exists()

    @pytest.mark.parametrize("status", [ReviewStatus.CONFIRMED, ReviewStatus.REVERSED])
    def test_confirmed_or_reversed_archives_keeps_rows(self, world, status):
        sub = world["plan_x"]
        pc = PriceChange.objects.create(
            subscription=sub, amount=Decimal("99.00"), currency="BDT", effective_from=date(2026, 1, 5)
        )
        charge_id = world["due_x"].charge_id
        due_id = world["due_x"].pk
        pay = make_payment(world["shared_x"], world["due_x"].member, world["owner"], status)
        c = client_for(world["owner"])
        assert c.delete(f"/api/subscriptions/{sub.pk}/", {"password": WORLD_PASS}, format="json").status_code == 204
        archived = Subscription.all_with_archived.get(pk=sub.pk)
        assert archived.archived_on is not None
        assert PriceChange.objects.filter(pk=pc.pk).exists()
        assert Charge.objects.filter(pk=charge_id).exists()
        assert Due.objects.filter(pk=due_id).exists()
        assert Payment.objects.filter(pk=pay.pk).exists()
        assert c.get(f"/api/subscriptions/{sub.pk}/").status_code == 404
        assert sub.pk not in {p["id"] for p in c.get("/api/subscriptions/").json()["results"]}
        assert AuditLog.objects.filter(action="plan.archived", entity_id=sub.pk).count() == 1

    def test_bad_password_no_delete_no_audit(self, world):
        sub = world["plan_y"]
        c = client_for(world["member"])
        before = audit_count()
        missing = c.delete(f"/api/subscriptions/{sub.pk}/", {}, format="json")
        wrong = c.delete(f"/api/subscriptions/{sub.pk}/", {"password": "nope"}, format="json")
        assert missing.status_code == wrong.status_code == 400
        assert missing.json()["error"]["code"] == "invalid_password"
        assert Subscription.objects.filter(pk=sub.pk).exists()
        assert audit_count() == before


@pytest.mark.django_db
class TestListFilters:
    def _seed_owner_plans(self, owner):
        client = client_for(owner)
        client.post(
            "/api/subscriptions/",
            plan_payload(plan_name="Alpha Stream", note="family share", rarely_used=False),
            format="json",
        )
        client.post(
            "/api/subscriptions/",
            plan_payload(
                plan_name="Beta Music",
                note="solo",
                currency="USD",
                amount="3.00",
                exchange_rate="110",
                rarely_used=True,
            ),
            format="json",
        )

    def test_search_and_filters(self, world):
        self._seed_owner_plans(world["owner"])
        sub_x = world["plan_x"]
        Subscription.objects.filter(pk=sub_x.pk).update(note="UNIQUEnote")
        c = client_for(world["owner"])
        all_ids = {p["id"] for p in c.get("/api/subscriptions/").json()["results"]}
        assert sub_x.pk in all_ids
        assert any(
            p["id"] == sub_x.pk for p in c.get("/api/subscriptions/?search=uniqueNOTE").json()["results"]
        )
        assert any(
            p["plan_name"] == "Alpha Stream"
            for p in c.get("/api/subscriptions/?search=alpha").json()["results"]
        )
        streaming = Category.objects.get(is_preset=True, name="Streaming")
        assert all(
            p["currency"] == "BDT"
            for p in c.get("/api/subscriptions/?currency=BDT").json()["results"]
        )
        assert all(
            p["id"] != sub_x.pk or p["status"] == sub_x.status
            for p in c.get(f"/api/subscriptions/?status={sub_x.status}").json()["results"]
        )
        assert all(
            p["plan_mode"] == "owner" for p in c.get("/api/subscriptions/?plan_mode=owner").json()["results"]
        )
        assert any(
            p["plan_name"] == "Beta Music"
            for p in c.get("/api/subscriptions/?rarely_used=true").json()["results"]
        )
        assert all(
            p["category"]["id"] == streaming.id
            for p in c.get(f"/api/subscriptions/?category={streaming.id}").json()["results"]
        )

    def test_invalid_filter_and_ordering(self, world):
        c = client_for(world["owner"])
        for url in (
            "/api/subscriptions/?ordering=evil",
            "/api/subscriptions/?status=not-a-status",
            "/api/subscriptions/?currency=EUR",
            "/api/subscriptions/?plan_mode=bad",
            "/api/subscriptions/?rarely_used=maybe",
        ):
            r = c.get(url)
            assert r.status_code == 400
            assert_error_shape(r)

    def test_ordering_asc_desc(self, world):
        self._seed_owner_plans(world["owner"])
        c = client_for(world["owner"])
        asc = c.get("/api/subscriptions/?ordering=plan_name").json()["results"]
        desc = c.get("/api/subscriptions/?ordering=-plan_name").json()["results"]
        names_asc = [p["plan_name"] for p in asc]
        names_desc = [p["plan_name"] for p in desc]
        assert names_asc == sorted(names_asc, key=str.lower)
        assert names_desc == sorted(names_desc, key=str.lower, reverse=True)

    def test_list_query_count_stable(self, world, django_assert_max_num_queries):
        c = client_for(world["owner"])

        def create_n(n):
            for i in range(n):
                c.post("/api/subscriptions/", plan_payload(plan_name=f"Bulk {i}"), format="json")

        create_n(3)
        with django_assert_max_num_queries(15):
            c.get("/api/subscriptions/")
        create_n(27)
        with django_assert_max_num_queries(15):
            c.get("/api/subscriptions/")


@pytest.mark.django_db
class TestCrossUserCatalog:
    def test_custom_ids_match_nonexistent_error(self, world):
        ca = client_for(world["owner"])
        cb = client_for(world["member"])
        custom_cat = ca.post("/api/categories/", {"name": "Only A Cat"}, format="json").json()["id"]
        streaming = Category.objects.get(is_preset=True, name="Streaming")
        custom_sn = ca.post(
            "/api/service-names/",
            {"name": "Only A Service", "category": streaming.id},
            format="json",
        ).json()["id"]
        ghost_cat = 9_999_991
        ghost_sn = 9_999_992
        for field, other_users_id, ghost_id in (
            ("service_name", custom_sn, ghost_sn),
            ("category", custom_cat, ghost_cat),
        ):
            r_other = cb.post(
                "/api/subscriptions/",
                plan_payload(**{field: other_users_id}),
                format="json",
            )
            r_ghost = cb.post(
                "/api/subscriptions/",
                plan_payload(**{field: ghost_id}),
                format="json",
            )
            assert r_other.status_code == r_ghost.status_code == 400
            assert r_other.json() == r_ghost.json()
            assert field in r_other.json()["error"]["fields"]


@pytest.mark.django_db
class TestAuditRows:
    def test_success_writes_one_row_each(self, world):
        c = client_for(world["owner"])
        before = audit_count()
        created = c.post("/api/subscriptions/", plan_payload(plan_name="Audit Plan"), format="json")
        sub_id = created.json()["id"]
        assert AuditLog.objects.filter(user=world["owner"], action="plan.created", entity_id=sub_id).count() == 1
        c.patch(f"/api/subscriptions/{sub_id}/", {"plan_name": "Audit Updated"}, format="json")
        assert AuditLog.objects.filter(user=world["owner"], action="plan.updated", entity_id=sub_id).count() == 1
        c.post(
            f"/api/subscriptions/{sub_id}/price-changes/",
            {"amount": "150.00", "effective_from": str(today_dhaka() + timedelta(days=30))},
            format="json",
        )
        assert AuditLog.objects.filter(user=world["owner"], action="price_change.created").count() == 1
        c.delete(f"/api/subscriptions/{sub_id}/", {"password": WORLD_PASS}, format="json")
        assert AuditLog.objects.filter(user=world["owner"], action="plan.deleted", entity_id=sub_id).count() == 1
        assert audit_count() == before + 4

    def test_rejected_writes_none(self, world):
        owner = client_for(world["owner"])
        outsider = client_for(world["outsider"])
        sub = world["plan_x"]
        PriceChange.objects.create(
            subscription=sub, amount=Decimal("100.00"), currency="BDT", effective_from=sub.start_date
        )
        before = audit_count()
        outsider.get(f"/api/subscriptions/{sub.pk}/")
        owner.patch(f"/api/subscriptions/{sub.pk}/", {"plan_mode": "reseller"}, format="json")
        owner.delete(f"/api/subscriptions/{sub.pk}/", {"password": "bad"}, format="json")
        owner.post(
            f"/api/subscriptions/{sub.pk}/price-changes/",
            {"amount": "0", "effective_from": "1990-01-01"},
            format="json",
        )
        owner.post(
            f"/api/subscriptions/{sub.pk}/price-changes/",
            {"amount": "50.00", "effective_from": str(today_dhaka() - timedelta(days=1))},
            format="json",
        )
        assert audit_count() == before


@pytest.mark.django_db
class TestCurrentAmount:
    def test_past_effective_beats_future_until_due(self, world):
        client = client_for(world["owner"])
        created = client.post(
            "/api/subscriptions/",
            plan_payload(
                plan_name="Dated Plan",
                start_date="1990-06-01",
                amount="100.00",
            ),
            format="json",
        )
        sub_id = created.json()["id"]
        assert created.json()["amount"] == "100.00"
        PriceChange.objects.create(
            subscription_id=sub_id,
            amount=Decimal("125.00"),
            currency="BDT",
            effective_from=date(2020, 1, 1),
        )
        client.post(
            f"/api/subscriptions/{sub_id}/price-changes/",
            {"amount": "999.00", "effective_from": str(today_dhaka() + timedelta(days=400))},
            format="json",
        )
        detail = client.get(f"/api/subscriptions/{sub_id}/").json()
        assert detail["amount"] == "125.00"

    def test_future_start_shows_earliest_price_on_list_and_detail(self, world):
        client = client_for(world["owner"])
        future_start = today_dhaka() + timedelta(days=30)
        created = client.post(
            "/api/subscriptions/",
            plan_payload(
                plan_name="Future Start",
                start_date=str(future_start),
                amount="88.50",
            ),
            format="json",
        )
        assert created.status_code == 201
        sub_id = created.json()["id"]
        assert created.json()["amount"] == "88.50"
        pc = PriceChange.objects.filter(subscription_id=sub_id).order_by("effective_from").first()
        assert pc is not None
        assert pc.effective_from == future_start
        assert pc.effective_from > today_dhaka()

        detail = client.get(f"/api/subscriptions/{sub_id}/").json()
        listed = next(p for p in client.get("/api/subscriptions/").json()["results"] if p["id"] == sub_id)
        assert detail["amount"] == "88.50"
        assert listed["amount"] == "88.50"
        assert detail["amount"] is not None
        assert listed["amount"] is not None

    def test_only_future_price_changes_use_earlier_on_list_and_detail(self, world):
        client = client_for(world["owner"])
        start = today_dhaka() + timedelta(days=20)
        later = start + timedelta(days=40)
        created = client.post(
            "/api/subscriptions/",
            plan_payload(
                plan_name="All Future Prices",
                start_date=str(start),
                amount="40.00",
            ),
            format="json",
        )
        sub_id = created.json()["id"]
        client.post(
            f"/api/subscriptions/{sub_id}/price-changes/",
            {"amount": "55.00", "effective_from": str(later)},
            format="json",
        )

        detail = client.get(f"/api/subscriptions/{sub_id}/").json()
        listed = next(p for p in client.get("/api/subscriptions/").json()["results"] if p["id"] == sub_id)
        assert detail["amount"] == "40.00"
        assert listed["amount"] == "40.00"
