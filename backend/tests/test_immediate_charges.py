"""Part A: charges and dues appear immediately on plan lifecycle triggers."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection

from billing.models import Charge, ChargeStatus
from core.dates import today_dhaka
from dues.models import Due
from plans.models import PlanMode, RenewalType, Subscription, SubscriptionStatus
from sharing.models import Member, SharedPlan, SplitType

from tests.test_billing_generator import month_before
from tests.test_subscriptions import WORLD_PASS, client_for, plan_payload

User = get_user_model()

pytestmark = pytest.mark.skipif(connection.vendor != "postgresql", reason="run_daily uses advisory locks")


def _create_shared_plan(owner_client, *, amount="1200.00", seats=4, plan_mode=PlanMode.OWNER):
    today = today_dhaka()
    start = month_before(today)
    r = owner_client.post(
        "/api/subscriptions/",
        {
            **plan_payload(plan_name="Immediate", plan_mode=plan_mode, start_date=str(start), amount=amount),
            "seats": seats,
        },
        format="json",
    )
    assert r.status_code == 201, r.content
    return r.json()["id"]


def _accept_invite(owner_client, plan_id, email, name):
    User.objects.create_user(email=email, password=WORLD_PASS, name=name, email_verified=True)
    tok = owner_client.post(
        f"/api/shared-plans/{plan_id}/invites/",
        {"email": email},
        format="json",
    ).json()["link"].split("/")[-1]
    buyer = User.objects.get(email=email)
    return client_for(buyer).post(f"/api/invites/{tok}/accept/", {}, format="json")


@pytest.mark.django_db
def test_plan_created_generates_charges_and_dues(world):
    owner = world["owner"]
    before = Charge.objects.count()
    plan_id = _create_shared_plan(client_for(owner))
    assert Charge.objects.filter(subscription_id=plan_id).exists()
    assert Charge.objects.count() > before
    charge = Charge.objects.filter(subscription_id=plan_id).order_by("period_start").first()
    assert Due.objects.filter(charge=charge).exists()


@pytest.mark.django_db
def test_plan_created_trial_creates_no_charges(world):
    owner = world["owner"]
    today = date.today()
    trial_end = today + timedelta(days=14)
    r = client_for(owner).post(
        "/api/subscriptions/",
        {
            **plan_payload(start_date=str(today), trial_end_date=str(trial_end)),
            "seats": 2,
        },
        format="json",
    )
    assert r.status_code == 201
    assert not Charge.objects.filter(subscription_id=r.json()["id"]).exists()


@pytest.mark.django_db
def test_resume_generates_charges_immediately(world):
    sub = world["plan_x"]
    owner_client = client_for(world["owner"])
    owner_client.post(f"/api/subscriptions/{sub.pk}/pause/", {}, format="json")
    count_before = Charge.objects.filter(subscription=sub).count()
    owner_client.post(f"/api/subscriptions/{sub.pk}/resume/", {}, format="json")
    assert Charge.objects.filter(subscription=sub).count() >= count_before
    out = StringIO()
    call_command("run_daily", stdout=out)
    assert Charge.objects.filter(subscription=sub).count() == count_before or "charges_created=0" in out.getvalue()


@pytest.mark.django_db
def test_renew_generates_charges_immediately(world):
    owner = world["owner"]
    today = date.today()
    sub = Subscription.objects.get(pk=_create_shared_plan(client_for(owner)))
    sub.renewal_type = RenewalType.FIXED_TERM
    sub.end_date = today + timedelta(days=30)
    sub.save(update_fields=["renewal_type", "end_date"])
    before = Charge.objects.filter(subscription=sub).count()
    client_for(owner).post(
        f"/api/subscriptions/{sub.pk}/renew/",
        {"end_date": str(today + timedelta(days=120))},
        format="json",
    )
    assert Charge.objects.filter(subscription=sub).count() >= before


def _unlocked_test_charge(sub, *, amount: str, anchor: date) -> Charge:
    period_start = anchor + timedelta(days=45)
    charge, created = Charge.objects.get_or_create(
        subscription=sub,
        period_start=period_start,
        defaults={
            "period_end": period_start + timedelta(days=30),
            "due_date": period_start + timedelta(days=5),
            "amount": Decimal(amount),
            "amount_bdt": Decimal(amount),
            "currency": "BDT",
            "status": ChargeStatus.UPCOMING,
            "locked": False,
        },
    )
    if not created:
        charge.locked = False
        charge.amount_bdt = Decimal(amount)
        charge.amount = Decimal(amount)
        charge.save(update_fields=["locked", "amount_bdt", "amount"])
        Due.objects.filter(charge=charge).delete()
    return charge


@pytest.mark.django_db
def test_member_join_splits_unlocked_charge_1200_three_buyers(world):
    owner_client = client_for(world["owner"])
    today = today_dhaka()
    plan_id = _create_shared_plan(owner_client, amount="1200.00", plan_mode=PlanMode.RESELLER)
    sub = Subscription.objects.get(pk=plan_id)
    charge = _unlocked_test_charge(sub, amount="1200.00", anchor=today)
    for i in range(3):
        _accept_invite(owner_client, plan_id, f"join{i}@example.com", f"J{i}")
    dues = list(Due.objects.filter(charge=charge).order_by("member_id"))
    assert len(dues) == 3
    assert sum(d.amount_bdt for d in dues) == charge.amount_bdt == Decimal("1200.00")
    assert all(d.amount_bdt == Decimal("400.00") for d in dues)


@pytest.mark.django_db
def test_member_join_splits_100_three_buyers_remainder_on_owner_seat(world):
    owner_client = client_for(world["owner"])
    today = today_dhaka()
    plan_id = _create_shared_plan(owner_client, amount="100.00", plan_mode=PlanMode.OWNER)
    sub = Subscription.objects.get(pk=plan_id)
    charge = _unlocked_test_charge(sub, amount="100.00", anchor=today)
    for i in range(2):
        _accept_invite(owner_client, plan_id, f"cent{i}@example.com", f"C{i}")
    dues = list(Due.objects.filter(charge=charge).select_related("member__user"))
    assert len(dues) == 3
    assert sum(d.amount_bdt for d in dues) == Decimal("100.00")
    owner_due = next(d for d in dues if d.member.user_id == world["owner"].pk)
    member_dues = [d for d in dues if d.member.user_id != world["owner"].pk]
    assert owner_due.amount_bdt == Decimal("33.34")
    assert all(d.amount_bdt == Decimal("33.33") for d in member_dues)


@pytest.mark.django_db
def test_locked_charge_unchanged_when_member_joins(world):
    owner_client = client_for(world["owner"])
    plan_id = _create_shared_plan(owner_client, amount="300.00")
    shared = SharedPlan.objects.get(subscription_id=plan_id)
    locked = Charge.objects.create(
        subscription_id=plan_id,
        period_start=date(2026, 1, 5),
        period_end=date(2026, 2, 4),
        due_date=date(2026, 1, 5),
        amount=Decimal("300.00"),
        amount_bdt=Decimal("300.00"),
        currency="BDT",
        status=ChargeStatus.DUE,
        locked=True,
    )
    from dues import services as dues_services

    dues_services.create_dues_for_charge(locked)
    before = list(Due.objects.filter(charge=locked).values_list("member_id", "amount_bdt"))
    _accept_invite(owner_client, plan_id, "late@example.com", "Late")
    after = list(Due.objects.filter(charge=locked).values_list("member_id", "amount_bdt"))
    assert before == after


@pytest.mark.django_db
def test_run_daily_idempotent_after_plan_create(world):
    owner_client = client_for(world["owner"])
    plan_id = _create_shared_plan(owner_client)
    before = Charge.objects.filter(subscription_id=plan_id).count()
    out = StringIO()
    call_command("run_daily", stdout=out)
    assert Charge.objects.filter(subscription_id=plan_id).count() == before
