from __future__ import annotations

from decimal import Decimal

import pytest

from dues.models import DueStatus
from dues import selectors as dues_selectors
from tests.test_subscriptions import client_for


@pytest.mark.django_db
def test_balance_equals_unpaid_dues(world_rich):
    world = world_rich
    member_row = world["member_row"]
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    snap = dues_selectors.member_balance(member_row)
    expected = Decimal(snap["total_unpaid"])
    open_sum = sum(
        (Decimal(item["amount"]) for item in snap["items"] if item["status"] in (DueStatus.DUE, DueStatus.PENDING)),
        Decimal("0"),
    )
    assert open_sum == expected
    detail = client_for(world["member"]).get(f"/api/me/shared-plans/{world['plan_x'].pk}/").json()
    api_open = sum((Decimal(d["amount"]) for d in detail.get("open_dues", [])), Decimal("0"))
    assert api_open == expected