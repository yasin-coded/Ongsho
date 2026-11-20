import os
import sys

# Before Django settings load — invite delivery crypto for outbox tests only.
if "pytest" in sys.argv[0] or any("pytest" in str(arg) for arg in sys.argv):
    from core.test_support.invite_delivery_keys import apply_test_invite_delivery_encryption_env

    apply_test_invite_delivery_encryption_env()

# Defaults for local pytest only; production values belong in `.env` (see `backend/.env.example`).
os.environ.setdefault("DEFAULT_FROM_EMAIL", "Ongsho <test@example.com>")
os.environ.setdefault("FRONTEND_BASE_URL", "http://localhost:5173")
os.environ.setdefault("REFRESH_COOKIE_SECURE", "False")
os.environ.setdefault("REFRESH_COOKIE_SAMESITE", "Lax")
os.environ.setdefault("FRONTEND_ORIGINS", "http://localhost:5173")

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def world(db):
    """Owner of plan X with member, member owns plan Y with owner as member, plus an outsider."""
    from decimal import Decimal

    from accounts.models import User
    from billing.models import Charge, ChargeStatus
    from catalog.models import Category, ServiceName
    from core.choices import Currency, PaymentMethod
    from dues.models import Due, DueStatus
    from core.dates import today_dhaka
    from plans.models import CycleUnit, PlanMode, RenewalType, Subscription, SubscriptionStatus
    from sharing.models import Member, MemberStatus, SharedPlan, SplitType

    owner = User.objects.create_user(email="owner@example.com", password="pass12345", name="Owner User")
    member = User.objects.create_user(email="member@example.com", password="pass12345", name="Member User")
    outsider = User.objects.create_user(email="outsider@example.com", password="pass12345", name="Outsider User")

    streaming = Category.objects.filter(is_preset=True, name="Streaming").first()
    netflix = ServiceName.objects.filter(is_preset=True, name="Netflix", category=streaming).first()

    sub_x = Subscription.objects.create(
        owner=owner,
        service_name=netflix,
        category=streaming,
        plan_name="Plan X",
        plan_mode=PlanMode.OWNER,
        currency=Currency.BDT,
        cycle_unit=CycleUnit.MONTH,
        cycle_count=1,
        anchor_day=5,
        start_date="2026-01-05",
        renewal_type=RenewalType.AUTO,
        status=SubscriptionStatus.ACTIVE,
        recommended_method=PaymentMethod.BKASH,
        billing_from=today_dhaka(),
    )
    shared_x = SharedPlan.objects.create(subscription=sub_x, split_type=SplitType.EQUAL)
    member_row_x = Member.objects.create(
        shared_plan=shared_x,
        user=member,
        share_type=SplitType.EQUAL,
        status=MemberStatus.ACTIVE,
        joined_on="2026-01-05",
    )
    charge_x = Charge.objects.create(
        subscription=sub_x,
        period_start="2026-02-05",
        period_end="2026-03-04",
        due_date="2026-02-04",
        amount=Decimal("1000.00"),
        currency=Currency.BDT,
        rate_used=None,
        amount_bdt=Decimal("1000.00"),
        status=ChargeStatus.DUE,
        locked=False,
    )
    due_x = Due.objects.create(charge=charge_x, member=member_row_x, amount_bdt=Decimal("500.00"), status=DueStatus.DUE)

    sub_y = Subscription.objects.create(
        owner=member,
        service_name=netflix,
        category=streaming,
        plan_name="Plan Y",
        plan_mode=PlanMode.OWNER,
        currency=Currency.BDT,
        cycle_unit=CycleUnit.MONTH,
        cycle_count=1,
        anchor_day=10,
        start_date="2026-01-10",
        renewal_type=RenewalType.AUTO,
        status=SubscriptionStatus.ACTIVE,
        recommended_method=PaymentMethod.NAGAD,
        billing_from=today_dhaka(),
    )
    shared_y = SharedPlan.objects.create(subscription=sub_y, split_type=SplitType.EQUAL)
    Member.objects.create(
        shared_plan=shared_y,
        user=owner,
        share_type=SplitType.EQUAL,
        status=MemberStatus.ACTIVE,
        joined_on="2026-01-10",
    )

    return {
        "owner": owner,
        "member": member,
        "outsider": outsider,
        "plan_x": sub_x,
        "plan_y": sub_y,
        "shared_x": shared_x,
        "shared_y": shared_y,
        "due_x": due_x,
    }
