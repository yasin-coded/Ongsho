from datetime import timedelta
from decimal import Decimal

import pytest

from billing.models import Charge, ChargeStatus
from core.choices import Currency
from core.dates import today_dhaka
from dues.models import Due, DueStatus
from plans.models import SubscriptionStatus

from tests.test_subscriptions import client_for


@pytest.mark.django_db
def test_pause_voids_upcoming_untouched_charges(world):
    sub = world["plan_x"]
    shared = world["shared_x"]
    future = today_dhaka() + timedelta(days=20)
    deletable = Charge.objects.create(
        subscription=sub,
        period_start=future,
        period_end=future + timedelta(days=29),
        due_date=future,
        amount=Decimal("100.00"),
        currency=Currency.BDT,
        amount_bdt=Decimal("100.00"),
        status=ChargeStatus.UPCOMING,
        locked=False,
    )
    Due.objects.create(
        charge=deletable, member=world["due_x"].member, amount_bdt=Decimal("50.00"), status=DueStatus.DUE
    )
    kept = Charge.objects.create(
        subscription=sub,
        period_start=future + timedelta(days=30),
        period_end=future + timedelta(days=59),
        due_date=future + timedelta(days=30),
        amount=Decimal("100.00"),
        currency=Currency.BDT,
        amount_bdt=Decimal("100.00"),
        status=ChargeStatus.UPCOMING,
        locked=False,
    )
    other_row = shared.members.get(user=world["member"])
    Due.objects.create(charge=kept, member=other_row, amount_bdt=Decimal("50.00"), status=DueStatus.PENDING)

    client = client_for(world["owner"])
    assert client.post(f"/api/subscriptions/{sub.pk}/pause/", format="json").status_code == 200
    assert not Charge.objects.filter(pk=deletable.pk).exists()
    assert Charge.objects.filter(pk=kept.pk).exists()
    sub.refresh_from_db()
    assert sub.status == SubscriptionStatus.PAUSED
    assert sub.paused_on == today_dhaka()
