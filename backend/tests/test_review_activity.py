from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from audit.models import AuditLog
from core.choices import PaymentMethod
from dues.models import Due, DueStatus
from payments.models import Payment, ReviewStatus
from sharing.models import Member
from tests.test_payment_decisions import _submit
from tests.test_subscriptions import assert_error_shape, client_for

User = get_user_model()


@pytest.mark.django_db
def test_review_anonymous_401(world):
    assert APIClient().get(f"/api/shared-plans/{world['plan_x'].pk}/review/").status_code == 401


@pytest.mark.django_db
def test_review_member_404(world):
    assert client_for(world["member"]).get(f"/api/shared-plans/{world['plan_x'].pk}/review/").status_code == 404


@pytest.mark.django_db
def test_review_shape_pending_decided_still_due(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    owner = client_for(world["owner"])
    member = client_for(world["member"])
    _submit(member, world["plan_x"].pk, due.pk, tid="REVIEW01")
    r = owner.get(f"/api/shared-plans/{world['plan_x'].pk}/review/")
    assert r.status_code == 200
    body = r.json()
    assert "plan" in body and body["plan"]["id"] == world["plan_x"].pk
    assert body["waiting"]["count"] == 1
    assert len(body["pending"]) == 1
    pend = body["pending"][0]
    assert pend["is_iou"] is False
    assert pend["covers"][0]["due_id"] == due.pk
    assert len(body["still_due"]) >= 0
    assert isinstance(body["decided"], list)
    assert "confirmed" in body


@pytest.mark.django_db
def test_review_pending_iou_flag(world):
    shared = world["shared_x"]
    charge = world["charge_x"]
    payer = world["member_row"]
    other = Member.objects.filter(shared_plan=shared).exclude(pk=payer.pk).first()
    due_other = Due.objects.get(charge=charge, member=other)
    due_other.status = DueStatus.DUE
    due_other.save(update_fields=["status"])
    pay_id = client_for(world["member"]).post(
        "/api/payments/",
        {
            "plan_id": world["plan_x"].pk,
            "due_ids": [due_other.pk],
            "method": PaymentMethod.BKASH,
            "transaction_id": "REVIEWIOU",
        },
        format="json",
    ).json()["payment_id"]
    body = client_for(world["owner"]).get(f"/api/shared-plans/{world['plan_x'].pk}/review/").json()
    item = next(p for p in body["pending"] if p["payment_id"] == pay_id)
    assert item["is_iou"] is True


@pytest.mark.django_db
def test_review_constant_query_count(world):
    owner = client_for(world["owner"])
    pid = world["plan_x"].pk

    def count_queries():
        with CaptureQueriesContext(connection) as ctx:
            r = owner.get(f"/api/shared-plans/{pid}/review/")
            assert r.status_code == 200
        return len(ctx)

    base = count_queries()
    from sharing.models import Member, MemberStatus, SplitType

    for i in range(8):
        u = User.objects.create_user(
            email=f"rev{i}@example.com",
            password="pass12345",
            name=f"Rev {i}",
            email_verified=True,
        )
        Member.objects.create(
            shared_plan=world["shared_x"],
            user=u,
            share_type=SplitType.EQUAL,
            status=MemberStatus.ACTIVE,
            joined_on=world["plan_x"].start_date,
        )
    assert count_queries() == base


@pytest.mark.django_db
def test_activity_ordering_tone_count(world):
    plan_id = world["plan_x"].pk
    owner = world["owner"]
    AuditLog.objects.filter(plan_id=plan_id).delete()
    for i in range(5):
        AuditLog.objects.create(
            user=owner,
            action="info.action",
            entity_type="X",
            entity_id=1,
            plan_id=plan_id,
            summary=f"extra {i}",
        )
    for action, summary, amt in (
        ("payment.submitted", "A sent payment", Decimal("10.00")),
        ("payment.confirmed", "You confirmed", Decimal("10.00")),
        ("payment.rejected", "You rejected", Decimal("10.00")),
        ("due.set_due", "Set back", Decimal("10.00")),
        ("member.leave_approved", "Left", None),
    ):
        AuditLog.objects.create(
            user=owner,
            action=action,
            entity_type="X",
            entity_id=1,
            plan_id=plan_id,
            summary=summary,
            amount=amt,
        )
    r = client_for(owner).get(f"/api/subscriptions/{plan_id}/")
    activity = r.json()["activity"]
    assert len(activity) == 10
    tones = {a["tone"] for a in activity}
    assert "pending" in tones
    assert "paid" in tones
    assert "due" in tones
    assert "info" in tones
    times = [a["created_at"] for a in activity]
    assert times == sorted(times, reverse=True)


@pytest.mark.django_db
def test_member_detail_rows_payment_fields(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    owner = client_for(world["owner"])
    today = world["today"]
    owner.post(
        f"/api/dues/{due.pk}/mark-paid/",
        {"date": str(today), "method": PaymentMethod.CASH, "note": "n"},
        format="json",
    )
    r = owner.get(f"/api/members/{due.member_id}/")
    assert r.status_code == 200
    row = next(x for x in r.json()["rows"] if x["due_id"] == due.pk)
    assert row["recorded_by_owner"] is True
    assert row["paid_on"] == str(today)


@pytest.mark.django_db
def test_members_endpoint_query_count_stable(world):
    owner = client_for(world["owner"])
    mid = world["member_row"].pk

    def count_queries():
        with CaptureQueriesContext(connection) as ctx:
            r = owner.get(f"/api/members/{mid}/")
            assert r.status_code == 200
        return len(ctx)

    base = count_queries()
    from sharing.models import Member, MemberStatus, SplitType

    for i in range(9):
        u = User.objects.create_user(
            email=f"memq{i}@example.com",
            password="pass12345",
            name=f"Mq {i}",
            email_verified=True,
        )
        Member.objects.create(
            shared_plan=world["shared_x"],
            user=u,
            share_type=SplitType.EQUAL,
            status=MemberStatus.ACTIVE,
            joined_on=world["plan_x"].start_date,
        )
    assert count_queries() == base


@pytest.mark.django_db
def test_review_error_shape_bad_plan(world):
    r = client_for(world["outsider"]).get(f"/api/shared-plans/{world['plan_x'].pk}/review/")
    assert r.status_code == 404
    assert_error_shape(r)
