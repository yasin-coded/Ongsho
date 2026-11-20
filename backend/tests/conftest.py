from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from billing.models import Charge
from billing import services as billing_services
from catalog.models import Category, ServiceName
from core.dates import today_dhaka
from dues.models import Due
from sharing.models import Member, MemberStatus, SharedPlan, SplitType
from plans.models import Subscription

from tests.test_billing_generator import month_before
from tests.test_subscriptions import WORLD_PASS, client_for, plan_payload

pytest_plugins = ["tests.world_rich_fixture"]

User = get_user_model()


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """Load migrations (preset categories) once per session."""
    with django_db_blocker.unblock():
        pass


@pytest.fixture(autouse=True)
def _catalog_presets(db):
    from tests.helpers import ensure_catalog_presets

    ensure_catalog_presets()


@pytest.fixture(autouse=True)
def _clear_django_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def world(db):
    streaming = Category.objects.get(is_preset=True, name="Streaming")
    netflix = ServiceName.objects.filter(is_preset=True, name="Netflix", category=streaming).first()
    owner = User.objects.create_user(
        email="owner@example.com", password=WORLD_PASS, name="Owner", email_verified=True
    )
    member = User.objects.create_user(
        email="member@example.com", password=WORLD_PASS, name="Member", email_verified=True
    )
    outsider = User.objects.create_user(
        email="outsider@example.com", password=WORLD_PASS, name="Outsider", email_verified=True
    )
    today = today_dhaka()
    start = month_before(today)
    owner_client = client_for(owner)
    r = owner_client.post(
        "/api/subscriptions/",
        {**plan_payload(start_date=str(start)), "seats": 3},
        format="json",
    )
    assert r.status_code == 201, r.content
    plan_x = Subscription.objects.get(pk=r.json()["id"])
    shared_x = SharedPlan.objects.get(subscription=plan_x)
    member_row = Member.objects.create(
        shared_plan=shared_x,
        user=member,
        share_type=SplitType.EQUAL,
        status=MemberStatus.ACTIVE,
        joined_on=plan_x.start_date,
    )
    member_client = client_for(member)
    r_y = member_client.post(
        "/api/subscriptions/",
        {**plan_payload(plan_name="Plan Y", start_date=str(start)), "seats": 2},
        format="json",
    )
    assert r_y.status_code == 201
    plan_y = Subscription.objects.get(pk=r_y.json()["id"])
    shared_y = SharedPlan.objects.get(subscription=plan_y)
    owner_as_member = Member.objects.create(
        shared_plan=shared_y,
        user=owner,
        share_type=SplitType.EQUAL,
        status=MemberStatus.ACTIVE,
        joined_on=plan_y.start_date,
    )
    billing_services.generate_missing_charges(plan_x, today)
    from dues import services as dues_services

    for ch in Charge.objects.filter(subscription=plan_x):
        dues_services.recalculate_dues(ch, today, force=True)
    charge_x = Charge.objects.filter(subscription=plan_x).order_by("-period_start").first()
    due_x = Due.objects.filter(charge=charge_x).exclude(member__user=owner).first()
    if due_x is None:
        due_x = Due.objects.filter(charge__subscription=plan_x).first()
    from django.utils import timezone
    from notifications.models import Notification

    Notification.objects.filter(user__in=[owner, member, outsider]).update(read_at=timezone.now())
    return {
        "owner": owner,
        "member": member,
        "outsider": outsider,
        "plan_x": plan_x,
        "plan_y": plan_y,
        "shared_x": shared_x,
        "shared_y": shared_y,
        "member_row": member_row,
        "owner_on_y": owner_as_member,
        "due_x": due_x,
        "charge_x": charge_x,
        "today": today,
    }
