from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from billing.models import Charge
from billing.services import generate_missing_charges
from core.choices import PaymentMethod
from dues.models import Due, DueStatus
from payments.models import Payment, PaymentAllocation, ReviewStatus
from plans.models import ExchangeRate
from tests.test_billing_generator import _plan
from tests.test_subscriptions import assert_error_shape, client_for, make_payment, plan_payload


@pytest.fixture
def owner(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        email="chg@example.com", password="pass12345", name="Chg", email_verified=True
    )

CHARGE_PATHS = [
    ("/api/charges/", "get"),
    ("/api/charges/generate/", "post"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("path,method", CHARGE_PATHS)
def test_charges_anonymous_401(path, method):
    client = APIClient()
    response = getattr(client, method)(path)
    assert response.status_code == 401
    assert_error_shape(response)


@pytest.mark.django_db
def test_charge_list_scoping_and_filters(owner):
    from django.contrib.auth import get_user_model

    other = get_user_model().objects.create_user(email="o2@example.com", password="pass12345", name="O2")
    mine = _plan(owner, billing_from=__import__("datetime").date(2026, 1, 5))
    theirs = _plan(other, billing_from=__import__("datetime").date(2026, 1, 5))
    generate_missing_charges(mine, __import__("datetime").date(2026, 1, 26))
    generate_missing_charges(theirs, __import__("datetime").date(2026, 1, 26))
    client = client_for(owner)
    listed = client.get("/api/charges/").json()
    ids = {row["id"] for row in listed["results"]}
    assert all(Charge.objects.get(pk=i).subscription.owner_id == owner.pk for i in ids)
    bad = client.get("/api/charges/?month=not-a-month")
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "validation_failed"


@pytest.mark.django_db
def test_generate_twice(world):
    sub = world["plan_x"]
    generate_missing_charges(sub, __import__("datetime").date(2026, 2, 15))
    client = client_for(world["owner"])
    first = client.post("/api/charges/generate/")
    second = client.post("/api/charges/generate/")
    assert first.status_code == second.status_code == 200
    assert second.json()["created"] == 0


@pytest.mark.django_db
def test_rate_correction_and_payments_started(world, owner=None):
    owner = world["owner"]
    sub = _plan(owner, currency="USD", billing_from=__import__("datetime").date(2026, 1, 5))
    ExchangeRate.objects.create(user=owner, rate_date=__import__("datetime").date(2026, 1, 1), usd_to_bdt=Decimal("120"))
    generate_missing_charges(sub, __import__("datetime").date(2026, 2, 5))
    charge = Charge.objects.filter(subscription=sub).first()
    client = client_for(owner)
    ok = client.patch(f"/api/charges/{charge.pk}/rate/", {"rate": "122.5"}, format="json")
    assert ok.status_code == 200
    member_row = world["shared_x"].members.get(user=world["member"])
    due = Due.objects.create(charge=charge, member=member_row, amount_bdt=Decimal("50.00"), status=DueStatus.DUE)
    payment = make_payment(world["shared_x"], member_row, world["member"], ReviewStatus.PENDING)
    PaymentAllocation.objects.create(payment=payment, due=due, amount_applied=Decimal("50.00"))
    blocked = client.patch(f"/api/charges/{charge.pk}/rate/", {"rate": "125"}, format="json")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "payments_started"


@pytest.mark.django_db
def test_other_users_charge_rate_404(world):
    sub = _plan(world["member"], billing_from=__import__("datetime").date(2026, 1, 5))
    generate_missing_charges(sub, __import__("datetime").date(2026, 1, 26))
    charge = Charge.objects.filter(subscription=sub).first()
    response = client_for(world["owner"]).patch(f"/api/charges/{charge.pk}/rate/", {"rate": "120"}, format="json")
    assert response.status_code == 404


@pytest.mark.django_db
def test_charge_list_query_count_stable(world, django_assert_max_num_queries):
    sub = world["plan_x"]
    generate_missing_charges(sub, __import__("datetime").date(2026, 2, 15))
    client = client_for(world["owner"])
    with django_assert_max_num_queries(4):
        client.get("/api/charges/")
