from datetime import date, timedelta

import pytest

from core.dates import today_dhaka
from tests.test_subscriptions import assert_error_shape, client_for, plan_payload


@pytest.mark.django_db
def test_create_next_renewal_valid(world):
    today = today_dhaka()
    from core.schedule import Schedule, next_due_date

    draft = Schedule(
        start_date=today,
        trial_end_date=None,
        anchor_day=today.day,
        cycle_unit="month",
        cycle_count=1,
        renewal_type="auto",
    )
    first_renewal = next_due_date(draft, today)
    assert first_renewal is not None
    payload = plan_payload(start_date=str(today), next_renewal_date=str(first_renewal))
    client = client_for(world["owner"])
    response = client.post("/api/subscriptions/", payload, format="json")
    assert response.status_code == 201
    from plans.models import Subscription

    sub = Subscription.objects.get(pk=response.json()["id"])
    assert sub.billing_from == first_renewal
    assert sub.anchor_day == first_renewal.day


@pytest.mark.django_db
def test_create_next_renewal_mismatch(world):
    today = today_dhaka()
    start = date(2020, 6, 5)
    wrong = today.replace(day=10)
    if wrong > today:
        wrong = today
    payload = plan_payload(
        start_date=str(start),
        next_renewal_date=str(wrong),
    )
    response = client_for(world["owner"]).post("/api/subscriptions/", payload, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "next_renewal_mismatch"


@pytest.mark.django_db
def test_create_next_renewal_with_trial_rejected(world):
    today = today_dhaka()
    payload = plan_payload(
        start_date=str(today),
        trial_end_date=str(today + timedelta(days=7)),
        next_renewal_date=str(today),
    )
    response = client_for(world["owner"]).post("/api/subscriptions/", payload, format="json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_create_next_renewal_future_start_rejected(world):
    today = today_dhaka()
    future = today + timedelta(days=10)
    payload = plan_payload(start_date=str(future), next_renewal_date=str(future))
    response = client_for(world["owner"]).post("/api/subscriptions/", payload, format="json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_patch_next_renewal_active(world):
    client = client_for(world["owner"])
    sub_id = world["plan_x"].pk
    today = today_dhaka()
    from billing.selectors import schedule_for_subscription
    from core.schedule import next_due_date

    target = next_due_date(schedule_for_subscription(world["plan_x"]), today)
    assert target is not None
    response = client.patch(f"/api/subscriptions/{sub_id}/", {"next_renewal_date": str(target)}, format="json")
    assert response.status_code == 200


@pytest.mark.django_db
def test_patch_next_renewal_paused_rejected(world):
    client = client_for(world["owner"])
    sub = world["plan_x"]
    client.post(f"/api/subscriptions/{sub.pk}/pause/")
    today = today_dhaka()
    response = client.patch(
        f"/api/subscriptions/{sub.pk}/",
        {"next_renewal_date": str(today)},
        format="json",
    )
    assert response.status_code in (400, 409)
    assert_error_shape(response)
