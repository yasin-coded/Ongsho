from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from core.dates import today_dhaka
from plans.models import ExchangeRate

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
    return User.objects.create_user(email="rate-a@example.com", password=STRONG, name="A", email_verified=True)


@pytest.fixture
def user_b(db):
    return User.objects.create_user(email="rate-b@example.com", password=STRONG, name="B", email_verified=True)


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
class TestExchangeRates:
    def test_create_and_list_order(self, user_a):
        client = client_for(user_a)
        today = today_dhaka()
        older = today - timedelta(days=2)
        client.post(
            "/api/exchange-rates/",
            {"rate_date": older.isoformat(), "usd_to_bdt": "120.5000"},
            format="json",
        )
        client.post(
            "/api/exchange-rates/",
            {"rate_date": today.isoformat(), "usd_to_bdt": "121.2500"},
            format="json",
        )
        page = client.get("/api/exchange-rates/").json()
        assert "results" in page
        assert len(page["results"]) == 2
        assert page["results"][0]["rate_date"] == today.isoformat()
        assert page["results"][0]["usd_to_bdt"] == "121.2500"

    def test_only_own_rates(self, user_a, user_b):
        ExchangeRate.objects.create(user=user_a, rate_date=today_dhaka(), usd_to_bdt=Decimal("100"), source="manual")
        ExchangeRate.objects.create(user=user_b, rate_date=today_dhaka(), usd_to_bdt=Decimal("200"), source="manual")
        assert len(client_for(user_a).get("/api/exchange-rates/").json()["results"]) == 1
        assert client_for(user_a).get("/api/exchange-rates/").json()["results"][0]["usd_to_bdt"] == "100.0000"

    def test_invalid_values(self, user_a):
        client = client_for(user_a)
        today = today_dhaka().isoformat()
        future = (today_dhaka() + timedelta(days=1)).isoformat()
        cases = [
            {"rate_date": today, "usd_to_bdt": "0"},
            {"rate_date": today, "usd_to_bdt": "-1"},
            {"rate_date": today, "usd_to_bdt": "abc"},
            {"rate_date": today, "usd_to_bdt": "1.23456"},
            {"rate_date": future, "usd_to_bdt": "120"},
        ]
        for payload in cases:
            response = client.post("/api/exchange-rates/", payload, format="json")
            assert response.status_code == 400
            assert_error_shape(response)

    def test_client_source_and_user_ignored(self, user_a):
        client = client_for(user_a)
        response = client.post(
            "/api/exchange-rates/",
            {
                "rate_date": today_dhaka().isoformat(),
                "usd_to_bdt": "119.9900",
                "source": "hacked",
                "user": 99999,
            },
            format="json",
        )
        assert response.status_code == 201
        assert response.json()["source"] == "manual"
        row = ExchangeRate.objects.get(pk=response.json()["id"])
        assert row.user_id == user_a.id
        assert row.source == "manual"

    def test_pagination_page_size_cap(self, user_a):
        client = client_for(user_a)
        today = today_dhaka()
        for i in range(30):
            ExchangeRate.objects.create(
                user=user_a,
                rate_date=today - timedelta(days=i),
                usd_to_bdt=Decimal("100") + i,
                source="manual",
            )
        page1 = client.get("/api/exchange-rates/?page_size=10").json()
        assert len(page1["results"]) == 10
        capped = client.get("/api/exchange-rates/?page_size=200").json()
        assert len(capped["results"]) <= 100

    def test_decimal_string_roundtrip(self, user_a):
        client = client_for(user_a)
        response = client.post(
            "/api/exchange-rates/",
            {"rate_date": today_dhaka().isoformat(), "usd_to_bdt": "123.45678"},
            format="json",
        )
        assert response.status_code == 400
        ok = client.post(
            "/api/exchange-rates/",
            {"rate_date": today_dhaka().isoformat(), "usd_to_bdt": "123.4560"},
            format="json",
        )
        assert ok.status_code == 201
        assert ok.json()["usd_to_bdt"] == "123.4560"
