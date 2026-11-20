"""Richer plan graph for matrix tests (two billing periods, multi-member, reseller)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from billing import services as billing_services
from billing.models import Charge
from dues import services as dues_services
from dues.models import Due
from catalog.models import Category, ServiceName
from notifications.models import Notification
from plans.models import PlanMode, Subscription
from sharing.models import Member, MemberStatus, SharedPlan, SplitType

from tests.test_billing_generator import month_before
from tests.test_subscriptions import WORLD_PASS, client_for, plan_payload

User = get_user_model()

def _bootstrap_charges(plan, real_today, *, min_count: int = 2) -> list[Charge]:
    """Advance simulated dates so generate_missing_charges can create past periods."""
    sim = plan.billing_from or real_today
    deadline = real_today + timedelta(days=366)
    while Charge.objects.filter(subscription=plan).count() < min_count and sim <= deadline:
        billing_services.generate_missing_charges(plan, sim)
        sim += timedelta(days=7)
    billing_services.generate_missing_charges(plan, real_today)
    charges = list(Charge.objects.filter(subscription=plan).order_by("period_start"))
    assert len(charges) >= min_count, f"expected >={min_count} charges on plan {plan.pk}, got {len(charges)}"
    for ch in charges:
        dues_services.recalculate_dues(ch, real_today, force=True)
    return charges


@pytest.fixture
def world_rich(db):
    streaming = Category.objects.get(is_preset=True, name="Streaming")
    netflix = ServiceName.objects.filter(is_preset=True, name="Netflix", category=streaming).first()
    from core.dates import today_dhaka

    today = today_dhaka()
    start = month_before(month_before(month_before(today)))

    owner = User.objects.create_user(
        email="rich-owner@example.com", password=WORLD_PASS, name="Rich Owner", email_verified=True
    )
    member_a = User.objects.create_user(
        email="rich-a@example.com", password=WORLD_PASS, name="Rich A", email_verified=True
    )
    member_b = User.objects.create_user(
        email="rich-b@example.com", password=WORLD_PASS, name="Rich B", email_verified=True
    )
    member_c = User.objects.create_user(
        email="rich-c@example.com", password=WORLD_PASS, name="Rich C", email_verified=True
    )
    outsider = User.objects.create_user(
        email="rich-out@example.com", password=WORLD_PASS, name="Outsider", email_verified=True
    )

    owner_client = client_for(owner)
    r = owner_client.post(
        "/api/subscriptions/",
        {**plan_payload(start_date=str(start), amount="1200.00"), "seats": 5},
        format="json",
    )
    assert r.status_code == 201, r.content
    plan_x = Subscription.objects.get(pk=r.json()["id"])
    shared_x = SharedPlan.objects.get(subscription=plan_x)
    member_rows = []
    for user in (member_a, member_b, member_c):
        member_rows.append(
            Member.objects.create(
                shared_plan=shared_x,
                user=user,
                share_type=SplitType.EQUAL,
                status=MemberStatus.ACTIVE,
                joined_on=plan_x.start_date,
            )
        )
    member_row = member_rows[0]

    charges_x = _bootstrap_charges(plan_x, today, min_count=2)
    charge_x = charges_x[-1]
    due_x = Due.objects.get(charge=charge_x, member=member_row)

    member_b_client = client_for(member_b)
    r_y = member_b_client.post(
        "/api/subscriptions/",
        {**plan_payload(plan_name="Rich Plan Y", start_date=str(start)), "seats": 3},
        format="json",
    )
    assert r_y.status_code == 201
    plan_y = Subscription.objects.get(pk=r_y.json()["id"])
    shared_y = SharedPlan.objects.get(subscription=plan_y)
    owner_on_y = Member.objects.create(
        shared_plan=shared_y,
        user=owner,
        share_type=SplitType.EQUAL,
        status=MemberStatus.ACTIVE,
        joined_on=plan_y.start_date,
    )

    r_res = owner_client.post(
        "/api/subscriptions/",
        {
            **plan_payload(plan_name="Rich Reseller", start_date=str(start), amount="900.00"),
            "plan_mode": PlanMode.RESELLER,
            "seats": 4,
        },
        format="json",
    )
    assert r_res.status_code == 201
    reseller_plan = Subscription.objects.get(pk=r_res.json()["id"])
    shared_reseller = SharedPlan.objects.get(subscription=reseller_plan)
    reseller_buyers = []
    reseller_member_rows = []
    for i, label in enumerate("abc"):
        u = User.objects.create_user(
            email=f"rich-buyer-{label}@example.com",
            password=WORLD_PASS,
            name=f"Buyer {label.upper()}",
            email_verified=True,
        )
        reseller_buyers.append(u)
        reseller_member_rows.append(
            Member.objects.create(
                shared_plan=shared_reseller,
                user=u,
                share_type=SplitType.EQUAL,
                status=MemberStatus.ACTIVE,
                joined_on=reseller_plan.start_date,
            )
        )
    charges_res = _bootstrap_charges(reseller_plan, today, min_count=2)
    charge_res = charges_res[-1]
    reseller_buyer_due = Due.objects.get(charge=charge_res, member=reseller_member_rows[0])
    reseller_other_due = (
        Due.objects.filter(charge=charge_res).exclude(member=reseller_member_rows[0]).order_by("id").first()
    )
    assert reseller_other_due is not None

    Notification.objects.filter(
        user__in=[owner, member_a, member_b, member_c, outsider, *reseller_buyers]
    ).update(read_at=timezone.now())

    return {
        "owner": owner,
        "member": member_a,
        "member_b": member_b,
        "member_c": member_c,
        "member_row": member_row,
        "member_rows": member_rows,
        "outsider": outsider,
        "plan_x": plan_x,
        "plan_y": plan_y,
        "shared_x": shared_x,
        "shared_y": shared_y,
        "owner_on_y": owner_on_y,
        "charges_x": charges_x,
        "charge_x": charge_x,
        "due_x": due_x,
        "today": today,
        "reseller_plan": reseller_plan,
        "shared_reseller": shared_reseller,
        "reseller_buyers": reseller_buyers,
        "reseller_member_rows": reseller_member_rows,
        "charge_res": charge_res,
        "reseller_buyer_due": reseller_buyer_due,
        "reseller_other_due": reseller_other_due,
    }