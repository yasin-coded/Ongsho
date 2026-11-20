from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from audit.models import AuditLog
from billing import services as billing_services
from billing.models import Charge, ChargeStatus
from core.choices import Currency
from core.dates import today_dhaka
from core.exceptions import ConflictError
from core.money import split_exact
from dues.models import Due, DueStatus
from dues import services as dues_services
from dues.splitting import members_for_charge
from dues.state import _ALLOWED, transition
from notifications.models import Notification
from plans.models import ExchangeRate, PlanMode, Subscription
from sharing.models import Member, MemberStatus, SharedPlan, SplitType

from tests.test_subscriptions import WORLD_PASS, client_for, plan_payload

User = get_user_model()
STRONG = "HorseBatteryStaple99"

_FORBIDDEN = [
    (a, b)
    for a in DueStatus
    for b in DueStatus
    if (a, b) not in _ALLOWED
]


@pytest.mark.django_db
def test_reseller_leftover_paisa_on_first_buyer(world):
    owner = world["owner"]
    client = client_for(owner)
    r = client.post(
        "/api/subscriptions/",
        {
            **plan_payload(
                plan_name="Reseller Dues",
                plan_mode=PlanMode.RESELLER,
                start_date=str(world["plan_x"].start_date),
            ),
            "seats": 3,
            "amount": "100.00",
        },
        format="json",
    )
    assert r.status_code == 201
    sub_id = r.json()["id"]
    shared = SharedPlan.objects.get(subscription_id=sub_id)
    buyers = []
    for i in range(3):
        email = f"buyer{i}@example.com"
        User.objects.create_user(email=email, password=STRONG, name=f"B{i}", email_verified=True)
        tok = client.post(f"/api/shared-plans/{sub_id}/invites/", {"email": email}, format="json").json()["link"].split("/")[-1]
        client_for(User.objects.get(email=email)).post(f"/api/invites/{tok}/accept/", {}, format="json")
        buyers.append(Member.objects.get(shared_plan=shared, user__email=email))
    today = world["today"]
    sub = shared.subscription
    due_day = max(today, sub.billing_from) + timedelta(days=30)
    charge = Charge.objects.create(
        subscription=sub,
        period_start=due_day - timedelta(days=30),
        period_end=due_day - timedelta(days=1),
        due_date=due_day,
        amount=Decimal("100.00"),
        amount_bdt=Decimal("100.00"),
        currency=Currency.BDT,
        status=ChargeStatus.DUE,
        locked=False,
    )
    dues_services.create_dues_for_charge(charge)
    dues = list(Due.objects.filter(charge=charge).order_by("member__joined_on", "member_id"))
    assert len(dues) == 3
    assert sum(d.amount_bdt for d in dues) == charge.amount_bdt
    assert dues[0].amount_bdt == split_exact(charge.amount_bdt, 3, 0)[0]


@pytest.mark.django_db
def test_join_mid_cycle_only_later_charges(world):
    shared = world["shared_x"]
    sub = world["plan_x"]
    early = Charge.objects.filter(subscription=sub).order_by("period_start").first()
    join_day = early.period_start + timedelta(days=15)
    guest = User.objects.create_user(
        email="midcycle@example.com", password=STRONG, name="Mid", email_verified=True
    )
    Member.objects.create(
        shared_plan=shared,
        user=guest,
        share_type=SplitType.EQUAL,
        status=MemberStatus.ACTIVE,
        joined_on=join_day,
    )
    assert guest.pk not in {m.user_id for m in members_for_charge(shared, early)}
    future_due = max(join_day, sub.billing_from, world["today"])
    future = Charge.objects.create(
        subscription=sub,
        period_start=future_due,
        period_end=future_due + timedelta(days=30),
        due_date=future_due,
        amount=Decimal("100.00"),
        amount_bdt=Decimal("100.00"),
        currency="BDT",
        status=ChargeStatus.DUE,
        locked=False,
    )
    dues_services.create_dues_for_charge(future)
    assert Due.objects.filter(charge=future, member__user=guest).exists()


@pytest.mark.django_db
def test_left_on_removes_due_status_only(world):
    today = world["today"]
    charge = world["charge_x"]
    guest = User.objects.create_user(
        email="leaver@example.com", password=STRONG, name="Leave", email_verified=True
    )
    row = Member.objects.create(
        shared_plan=world["shared_x"],
        user=guest,
        share_type=SplitType.EQUAL,
        status=MemberStatus.ACTIVE,
        joined_on=world["plan_x"].start_date,
        left_on=charge.period_start,
    )
    orph = Due.objects.create(charge=charge, member=row, amount_bdt=Decimal("10.00"), status=DueStatus.DUE)
    paid_copy = Due.objects.create(
        charge=charge,
        member=Member.objects.create(
            shared_plan=world["shared_x"],
            user=User.objects.create_user(email="paid-leaver@x.com", password=STRONG, name="PL", email_verified=True),
            share_type=SplitType.EQUAL,
            status=MemberStatus.LEFT,
            joined_on=world["plan_x"].start_date,
            left_on=today,
        ),
        amount_bdt=Decimal("10.00"),
        status=DueStatus.PAID,
    )
    dues_services.recalculate_dues(charge, today, force=True)
    assert not Due.objects.filter(pk=orph.pk).exists()
    assert not Due.objects.filter(charge=charge, member=row, status=DueStatus.DUE).exists()
    assert Due.objects.filter(pk=paid_copy.pk, status=DueStatus.PAID).exists()


@pytest.mark.django_db
def test_recalculate_touches_only_due_not_owner_paid(world):
    charge = world["charge_x"]
    member_due = world["due_x"]
    member_due.status = DueStatus.DUE
    member_due.amount_bdt = Decimal("1.00")
    member_due.save(update_fields=["status", "amount_bdt"])
    owner_row = world["shared_x"].members.get(user=world["owner"])
    owner_due = Due.objects.get(charge=charge, member=owner_row)
    owner_due.status = DueStatus.PAID
    owner_due.amount_bdt = Decimal("1.00")
    owner_due.save(update_fields=["status", "amount_bdt"])
    guest = User.objects.create_user(email="pend-waive@x.com", password=STRONG, name="PW", email_verified=True)
    grow = Member.objects.create(
        shared_plan=world["shared_x"],
        user=guest,
        share_type=SplitType.EQUAL,
        status=MemberStatus.ACTIVE,
        joined_on=world["plan_x"].start_date,
    )
    pending = Due.objects.create(charge=charge, member=grow, amount_bdt=Decimal("5.00"), status=DueStatus.PENDING)
    guest2 = User.objects.create_user(email="waived-only@x.com", password=STRONG, name="W", email_verified=True)
    grow2 = Member.objects.create(
        shared_plan=world["shared_x"],
        user=guest2,
        share_type=SplitType.EQUAL,
        status=MemberStatus.ACTIVE,
        joined_on=world["plan_x"].start_date,
    )
    waived = Due.objects.create(charge=charge, member=grow2, amount_bdt=Decimal("6.00"), status=DueStatus.WAIVED)
    old_pending = pending.amount_bdt
    old_waived = waived.amount_bdt
    charge.locked = False
    charge.save(update_fields=["locked"])
    dues_services.recalculate_dues(charge, world["today"], force=True)
    member_due.refresh_from_db()
    owner_due.refresh_from_db()
    pending.refresh_from_db()
    waived.refresh_from_db()
    assert member_due.amount_bdt != Decimal("1.00")
    assert owner_due.amount_bdt == Decimal("1.00")
    assert pending.amount_bdt == old_pending
    assert waived.amount_bdt == old_waived


@pytest.mark.django_db
def test_amount_changed_notification_targeting(world):
    charge = world["charge_x"]
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.amount_bdt = Decimal("1.00")
    due.save(update_fields=["status", "amount_bdt"])
    charge.locked = False
    charge.save(update_fields=["locked"])
    Notification.objects.filter(kind="amount_changed").delete()
    dues_services.recalculate_dues(charge, world["today"], force=True)
    notes = list(Notification.objects.filter(kind="amount_changed"))
    assert len(notes) == 1
    assert notes[0].user_id == due.member.user_id
    assert "share changed" in notes[0].title.lower()


@pytest.mark.django_db
def test_blocked_custom_split_notifies_once(world):
    shared = world["shared_x"]
    shared.split_type = SplitType.CUSTOM
    shared.save(update_fields=["split_type"])
    for m in shared.members.all():
        m.share_type = SplitType.CUSTOM
        m.share_value = Decimal("40.00")
        m.save(update_fields=["share_type", "share_value"])
    latest = (
        Charge.objects.filter(subscription=world["plan_x"]).order_by("-due_date").values_list("due_date", flat=True).first()
        or world["today"]
    )
    due_day = latest + timedelta(days=120)
    charge = Charge.objects.create(
        subscription=world["plan_x"],
        period_start=due_day,
        period_end=due_day + timedelta(days=30),
        due_date=due_day + timedelta(days=30),
        amount=Decimal("100.00"),
        amount_bdt=Decimal("100.00"),
        currency="BDT",
        status=ChargeStatus.DUE,
        locked=False,
    )
    assert dues_services.create_dues_for_charge(charge) == 0
    assert Notification.objects.filter(kind="split_blocked").count() == 1
    assert dues_services.create_dues_for_charge(charge) == 0
    assert Notification.objects.filter(kind="split_blocked").count() == 1


@pytest.mark.django_db
def test_fix_split_creates_dues_on_locked_charge(world):
    shared = world["shared_x"]
    owner_m = shared.members.get(user=world["owner"])
    member_m = world["member_row"]
    owner_m.share_type = SplitType.CUSTOM
    owner_m.share_value = Decimal("40.00")
    member_m.share_type = SplitType.CUSTOM
    member_m.share_value = Decimal("60.00")
    owner_m.save()
    member_m.save()
    shared.split_type = SplitType.CUSTOM
    shared.save()
    charge = world["charge_x"]
    charge.locked = True
    charge.save(update_fields=["locked"])
    Due.objects.filter(charge=charge).delete()
    dues_services.recalculate_dues(charge, world["today"], force=True)
    assert Due.objects.filter(charge=charge).count() >= 2


@pytest.mark.django_db
def test_leave_unpaid_waive_and_keep(world):
    today = world["today"]
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    member = due.member
    from sharing import services as sharing_services

    sharing_services.owner_leave_decision(
        world["owner"],
        member.pk,
        today=today,
        approve=True,
        leave_date=today,
        unpaid="waive",
    )
    due.refresh_from_db()
    assert due.status == DueStatus.WAIVED
    assert "left" in due.waiver_note.lower()
    assert AuditLog.objects.filter(action="due_status", entity_id=due.pk).exists()

    guest = User.objects.create_user(
        email="keep-unpaid@example.com", password=STRONG, name="K", email_verified=True
    )
    grow = Member.objects.create(
        shared_plan=world["shared_x"],
        user=guest,
        share_type=SplitType.EQUAL,
        status=MemberStatus.ACTIVE,
        joined_on=today,
    )
    keep_due = Due.objects.create(
        charge=world["charge_x"], member=grow, amount_bdt=Decimal("12.00"), status=DueStatus.DUE
    )
    sharing_services.owner_leave_decision(
        world["owner"],
        grow.pk,
        today=today,
        approve=True,
        leave_date=today,
        unpaid="keep",
    )
    assert Due.objects.filter(pk=keep_due.pk, status=DueStatus.DUE).exists()


@pytest.mark.django_db
def test_rate_correction_forces_recalculation(world):
    today = world["today"]
    charge = world["charge_x"]
    charge.currency = Currency.USD
    charge.amount = Decimal("10.00")
    charge.rate_used = Decimal("110.0000")
    charge.amount_bdt = Decimal("1100.00")
    charge.locked = False
    charge.save(update_fields=["currency", "amount", "rate_used", "amount_bdt", "locked"])
    member_due = world["due_x"]
    member_amount = member_due.amount_bdt
    ExchangeRate.objects.create(user=world["owner"], rate_date=today, usd_to_bdt=Decimal("110.0000"), source="manual")
    billing_services.correct_rate(world["owner"], charge.pk, Decimal("120.0000"), today)
    charge.refresh_from_db()
    assert charge.amount_bdt == Decimal("1200.00")
    dues_services.recalculate_dues(charge, today, force=True)
    member_due.refresh_from_db()
    assert member_due.amount_bdt != member_amount


@pytest.mark.django_db
def test_ensure_dues_twice_creates_nothing_new(world):
    today = world["today"]
    first = dues_services.ensure_dues(today)
    count = Due.objects.count()
    second = dues_services.ensure_dues(today)
    assert Due.objects.count() == count
    assert second == 0 or first >= 0


@pytest.mark.django_db(transaction=True)
def test_concurrent_create_dues_unique(world):
    charge = world["charge_x"]
    expected = len(members_for_charge(world["shared_x"], charge))
    Due.objects.filter(charge=charge).delete()
    from tests.helpers import run_concurrently

    def work():
        return dues_services.create_dues_for_charge(charge)

    _, errors = run_concurrently([work, work])
    integrity = [e for e in errors if isinstance(e, IntegrityError)]
    assert len(integrity) <= 1
    assert Due.objects.filter(charge=charge).count() == expected


@pytest.mark.django_db
def test_create_dues_idempotent_per_charge(world):
    charge = world["charge_x"]
    expected = len(members_for_charge(world["shared_x"], charge))
    Due.objects.filter(charge=charge).delete()
    dues_services.create_dues_for_charge(charge)
    dues_services.create_dues_for_charge(charge)
    assert Due.objects.filter(charge=charge).count() == expected


@pytest.mark.django_db
@pytest.mark.parametrize("src,dst", _FORBIDDEN)
def test_illegal_due_transition_invalid_code(world, src, dst):
    due = Due.objects.get(pk=world["due_x"].pk)
    due.status = src
    due.save(update_fields=["status"])
    with pytest.raises(ConflictError) as exc:
        transition(due, dst, world["owner"])
    assert exc.value.code == "invalid_due_status"
    due.refresh_from_db()
    assert due.status == src
