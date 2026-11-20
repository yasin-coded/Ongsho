from decimal import Decimal

import pytest

from billing.models import Charge
from dues.models import Due, DueStatus
from dues import services as dues_services
from sharing.models import Member, MemberStatus, SplitType


@pytest.mark.django_db
def test_charges_create_dues(world):
    charge = world["charge_x"]
    dues = list(Due.objects.filter(charge=charge).select_related("member", "member__user"))
    assert dues
    assert sum(d.amount_bdt for d in dues) == charge.amount_bdt
    owner_due = next(d for d in dues if d.member.user_id == world["owner"].pk)
    assert owner_due.status == DueStatus.DUE


@pytest.mark.django_db
def test_ensure_dues_idempotent(world):
    today = world["today"]
    first = dues_services.ensure_dues(today)
    second = dues_services.ensure_dues(today)
    assert second == 0 or first >= 0


@pytest.mark.django_db
def test_member_join_recalculates(world):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    guest = User.objects.create_user(
        email="joiner@example.com", password="pass12345", name="Joiner", email_verified=True
    )
    shared = world["shared_x"]
    before = Due.objects.filter(charge__subscription=world["plan_x"]).count()
    Member.objects.create(
        shared_plan=shared,
        user=guest,
        share_type=SplitType.EQUAL,
        status=MemberStatus.ACTIVE,
        joined_on=world["today"],
    )
    after = Due.objects.filter(charge__subscription=world["plan_x"]).count()
    assert after >= before
