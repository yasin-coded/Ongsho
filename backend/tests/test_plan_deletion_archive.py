from __future__ import annotations

import pytest

from dues.models import DueStatus
from plans.models import Subscription
from tests.test_payments import _submit
from tests.test_subscriptions import WORLD_PASS, client_for


@pytest.mark.django_db
def test_delete_archives_when_confirmed_payments(world_rich):
    world = world_rich
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    owner = client_for(world["owner"])
    pay_id = _submit(
        client_for(world["member"]), world["plan_x"].pk, [due.pk], transaction_id="DELARC01"
    ).json()["payment_id"]
    owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    r = owner.delete(
        f"/api/subscriptions/{world['plan_x'].pk}/",
        {"password": WORLD_PASS},
        format="json",
    )
    assert r.status_code in (200, 204)
    sub = Subscription.all_with_archived.get(pk=world["plan_x"].pk)
    assert sub.archived_on is not None