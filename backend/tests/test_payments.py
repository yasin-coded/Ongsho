from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from notifications.models import Notification
from payments.models import Payment, ReviewStatus
from rest_framework.test import APIClient

from core.choices import PaymentMethod
from dues.models import Due, DueStatus
from tests.test_subscriptions import assert_error_shape, client_for

User = get_user_model()
TID = "AB12CD34EF"


def _submit(client, plan_id, due_ids, **extra):
    body = {
        "plan_id": plan_id,
        "due_ids": due_ids,
        "method": PaymentMethod.BKASH,
        "transaction_id": TID,
        **extra,
    }
    return client.post("/api/payments/", body, format="json")


@pytest.mark.django_db
def test_submit_anonymous_401():
    assert APIClient().post("/api/payments/", {}, format="json").status_code == 401


@pytest.mark.django_db
def test_submit_success_notifies_owner(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    r = _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk])
    assert r.status_code == 201
    assert "payment_id" in r.json()
    due.refresh_from_db()
    assert due.status == DueStatus.PENDING
    assert Notification.objects.filter(user=world["owner"], kind="payment_submitted").exists()


@pytest.mark.django_db
def test_owner_cannot_submit(world):
    due = world["due_x"]
    r = _submit(client_for(world["owner"]), world["plan_x"].pk, [due.pk])
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "owner_cannot_submit"


@pytest.mark.django_db
def test_outsider_submit_404(world):
    r = _submit(client_for(world["outsider"]), world["plan_x"].pk, [world["due_x"].pk])
    assert r.status_code == 404


@pytest.mark.django_db
def test_due_not_open(world):
    due = world["due_x"]
    due.status = DueStatus.PAID
    due.save(update_fields=["status"])
    r = _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk])
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "due_not_open"


@pytest.mark.django_db
def test_duplicate_tid_any_case(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    member = client_for(world["member"])
    assert _submit(member, world["plan_x"].pk, [due.pk], transaction_id="ab12 cd34ef").status_code == 201
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    r = _submit(member, world["plan_x"].pk, [due.pk], transaction_id="AB12CD34EF")
    assert r.status_code == 400
    assert "transaction_id" in r.json()["error"]["fields"]


@pytest.mark.django_db
def test_card_like_tid_rejected(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    r = _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk], transaction_id="4111111111111111")
    assert r.status_code == 400
    assert_error_shape(r)


@pytest.mark.django_db
def test_amount_mismatch(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    r = _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk], amount="1.00")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "amount_mismatch"


@pytest.mark.django_db(transaction=True)
def test_concurrent_submit_same_due(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    member = world["member"]
    from tests.helpers import run_concurrently

    results, _ = run_concurrently(
        [
            lambda: _submit(client_for(member), world["plan_x"].pk, [due.pk], transaction_id="TIDONE01").status_code,
            lambda: _submit(client_for(member), world["plan_x"].pk, [due.pk], transaction_id="TIDTWO02").status_code,
        ]
    )
    assert Payment.objects.filter(shared_plan=world["shared_x"], review_status=ReviewStatus.PENDING).count() == 1
    assert 201 in results
    assert 409 in results
