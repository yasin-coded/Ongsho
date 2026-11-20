"""PATCH plan metadata must not be dropped when next_renewal_date is present."""

from __future__ import annotations

import pytest

from plans.models import Subscription
from plans.selectors import display_next_renewal
from tests.test_subscriptions import client_for

pytestmark = pytest.mark.django_db


def test_patch_note_persists_when_next_renewal_date_sent(world):
    sub = world["plan_x"]
    nxt = display_next_renewal(sub)
    if not nxt:
        pytest.skip("fixture plan has no displayable next renewal")
    oc = client_for(world["owner"])
    assert (
        oc.patch(
            f"/api/subscriptions/{sub.pk}/",
            {"note": "Team shares ChatGPT", "next_renewal_date": nxt},
            format="json",
        ).status_code
        == 200
    )
    assert Subscription.objects.get(pk=sub.pk).note == "Team shares ChatGPT"