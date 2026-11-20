import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from catalog.models import Category, ServiceName

User = get_user_model()
STRONG = "HorseBatteryStaple99"


def assert_error_shape(response):
    assert response.status_code >= 400
    body = response.json()
    assert set(body.keys()) == {"error"}
    err = body["error"]
    assert set(err.keys()) == {"code", "message", "fields"}


@pytest.fixture
def user_a(db):
    return User.objects.create_user(email="a@example.com", password=STRONG, name="A", email_verified=True)


@pytest.fixture
def user_b(db):
    return User.objects.create_user(email="b@example.com", password=STRONG, name="B", email_verified=True)


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


ANON_ENDPOINTS = ["/api/categories/", "/api/service-names/", "/api/exchange-rates/"]


@pytest.mark.django_db
@pytest.mark.parametrize("path", ANON_ENDPOINTS)
def test_anonymous_returns_401_envelope(path):
    response = APIClient().get(path)
    assert response.status_code == 401
    assert_error_shape(response)


@pytest.mark.django_db
def test_new_user_sees_presets(user_a):
    client = client_for(user_a)
    cats = client.get("/api/categories/").json()
    names = client.get("/api/service-names/").json()
    assert len(cats) == 8
    assert len(names) == 34
    assert all(c["is_preset"] for c in cats)
    assert all(n["is_preset"] for n in names)


@pytest.mark.django_db
class TestCategoryIsolation:
    def test_custom_visible_only_to_owner(self, user_a, user_b):
        ca = client_for(user_a)
        cb = client_for(user_b)
        created = ca.post("/api/categories/", {"name": "My Stream"}, format="json")
        assert created.status_code == 201
        cat_id = created.json()["id"]
        assert any(c["id"] == cat_id for c in ca.get("/api/categories/").json())
        assert not any(c["id"] == cat_id for c in cb.get("/api/categories/").json())

    def test_service_name_isolation_and_category_filter(self, user_a, user_b):
        ca = client_for(user_a)
        cb = client_for(user_b)
        custom_cat = ca.post("/api/categories/", {"name": "Personal Tools"}, format="json").json()
        cat_id = custom_cat["id"]
        streaming = Category.objects.get(is_preset=True, name="Streaming")
        sn = ca.post(
            "/api/service-names/",
            {"name": "My Netflix Clone", "category": cat_id},
            format="json",
        )
        assert sn.status_code == 201
        sid = sn.json()["id"]
        assert any(x["id"] == sid for x in ca.get("/api/service-names/").json())
        assert not any(x["id"] == sid for x in cb.get("/api/service-names/").json())
        assert not any(x["id"] == sid for x in cb.get(f"/api/service-names/?category={cat_id}").json())
        bad = cb.post(
            "/api/service-names/",
            {"name": "Sneaky", "category": cat_id},
            format="json",
        )
        assert bad.status_code == 400
        assert_error_shape(bad)
        assert "category" in bad.json()["error"]["fields"]
        assert cb.get(f"/api/service-names/?category={streaming.id}").json()


@pytest.mark.django_db
class TestDuplicatesAndNames:
    def test_category_duplicate_preset_case(self, user_a):
        client = client_for(user_a)
        preset = Category.objects.filter(is_preset=True).first().name
        response = client.post("/api/categories/", {"name": preset.upper()}, format="json")
        assert response.status_code == 400
        assert "name" in response.json()["error"]["fields"]

    def test_category_duplicate_own(self, user_a):
        client = client_for(user_a)
        client.post("/api/categories/", {"name": "UniqueCat"}, format="json")
        dup = client.post("/api/categories/", {"name": "uniquecat"}, format="json")
        assert dup.status_code == 400

    def test_two_users_same_category_name(self, user_a, user_b):
        ca = client_for(user_a)
        cb = client_for(user_b)
        assert ca.post("/api/categories/", {"name": "Shared Label"}, format="json").status_code == 201
        assert cb.post("/api/categories/", {"name": "Shared Label"}, format="json").status_code == 201

    def test_service_name_same_in_different_categories(self, user_a):
        client = client_for(user_a)
        music = Category.objects.get(is_preset=True, name="Music")
        streaming = Category.objects.get(is_preset=True, name="Streaming")
        assert client.post(
            "/api/service-names/", {"name": "MyApp", "category": music.id}, format="json"
        ).status_code == 201
        assert client.post(
            "/api/service-names/", {"name": "MyApp", "category": streaming.id}, format="json"
        ).status_code == 201

    def test_service_duplicate_preset_in_category(self, user_a):
        client = client_for(user_a)
        streaming = Category.objects.get(is_preset=True, name="Streaming")
        preset_name = ServiceName.objects.filter(is_preset=True, category=streaming).first().name
        response = client.post(
            "/api/service-names/",
            {"name": preset_name.lower(), "category": streaming.id},
            format="json",
        )
        assert response.status_code == 400

    def test_name_validation_and_trim(self, user_a):
        client = client_for(user_a)
        for payload in [{"name": ""}, {"name": "   "}]:
            response = client.post("/api/categories/", payload, format="json")
            assert response.status_code == 400
            assert "name" in response.json()["error"]["fields"]
        long_name = "x" * 129
        too_long = client.post("/api/categories/", {"name": long_name}, format="json")
        assert too_long.status_code == 400
        trimmed = client.post("/api/categories/", {"name": "  Trimmed Cat  "}, format="json")
        assert trimmed.status_code == 201
        assert trimmed.json()["name"] == "Trimmed Cat"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path",
    ["/api/categories/", "/api/service-names/", "/api/exchange-rates/"],
)
def test_disallowed_methods_return_405(path, user_a):
    client = client_for(user_a)
    for method in ("put", "patch", "delete"):
        response = getattr(client, method)(path, {}, format="json")
        assert response.status_code == 405
        assert_error_shape(response)
        assert response.json()["error"]["code"] == "method_not_allowed"


@pytest.mark.django_db
def test_service_names_query_count(user_a, django_assert_max_num_queries):
    client = client_for(user_a)
    with django_assert_max_num_queries(2):
        client.get("/api/service-names/")
