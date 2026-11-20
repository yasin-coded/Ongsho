"""Owner plan detail confirmed_so_far for the progress bar."""

from decimal import Decimal

import pytest

from dues.models import Due, DueStatus
from payments.models import Payment, PaymentAllocation, ReviewStatus
from core.choices import PaymentMethod

from tests.test_subscriptions import client_for


@pytest.mark.django_db
def test_plan_detail_confirmed_so_far_when_members_paid(world):
    due = world["due_x"]
    due.status = DueStatus.PAID
    due.save(update_fields=["status"])
    for other in Due.objects.filter(charge=due.charge).exclude(pk=due.pk):
        if other.status != DueStatus.WAIVED:
            other.status = DueStatus.PAID
            other.save(update_fields=["status"])

    r = client_for(world["owner"]).get(f"/api/subscriptions/{world['plan_x'].pk}/")
    assert r.status_code == 200
    csf = r.json()["confirmed_so_far"]
    assert csf is not None
    assert Decimal(csf["pending"]) == Decimal("0")
    assert Decimal(csf["paid"]) == Decimal(csf["expected"])
    assert Decimal(csf["expected"]) > 0
