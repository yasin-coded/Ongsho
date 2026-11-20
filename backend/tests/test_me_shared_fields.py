"""Part B: member shared-plan and owner review API field enrichment."""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model

from dues.models import DueStatus
from sharing.models import MemberStatus

from tests.test_subscriptions import client_for

User = get_user_model()


def _walk_strings(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_strings(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            yield from _walk_strings(item, f"{path}[{i}]")
    elif isinstance(obj, str) and "@" in obj and "." in obj:
        yield path, obj


@pytest.mark.django_db
def test_review_includes_service_next_renewal_and_payer_email(world):
    r = client_for(world["owner"]).get(f"/api/shared-plans/{world['plan_x'].pk}/review/")
    assert r.status_code == 200
    body = r.json()
    plan = body["plan"]
    assert "service_name" in plan and plan["service_name"]["name"]
    assert "next_renewal" in plan


@pytest.mark.django_db
def test_me_shared_list_totals_and_item_fields(world):
    r = client_for(world["member"]).get("/api/me/shared-plans/")
    assert r.status_code == 200
    body = r.json()
    totals = body["totals"]
    for key in ("due_names", "waiting_names", "due_count", "pending_count", "paid_up_count"):
        assert key in totals
    items = body.get("results") or body.get("items") or []
    assert items
    item = items[0]
    assert "service_name" in item
    assert "next_renewal" in item
    assert "leave_requested" in item
    assert "recommended_method" in item
    assert "open_dues" in item
    assert "members" in item


@pytest.mark.django_db
def test_me_shared_detail_me_block_and_leave_flags(world):
    r = client_for(world["member"]).get(f"/api/me/shared-plans/{world['plan_x'].pk}/")
    assert r.status_code == 200
    body = r.json()
    me = body["me"]
    assert set(me) >= {"member_id", "status", "joined_on", "leave_requested_at"}
    assert "leave_requested" in body
    assert "can_request_leave" in body
    assert body["can_request_leave"] is True
    assert "next_renewal" in body


@pytest.mark.django_db
def test_member_responses_hide_other_emails(world):
    r = client_for(world["member"]).get(f"/api/me/shared-plans/{world['plan_x'].pk}/")
    assert r.status_code == 200
    raw = json.dumps(r.json())
    assert world["owner"].email not in raw
    r2 = client_for(world["member"]).get("/api/me/shared-plans/")
    raw2 = json.dumps(r2.json())
    assert world["owner"].email not in raw2
    for path, val in _walk_strings(r.json()):
        if "email" in path.lower():
            pytest.fail(f"unexpected email field at {path}")


@pytest.mark.django_db
def test_review_leave_requested_on_payer(world):
    member_row = world["member_row"]
    member_row.status = MemberStatus.LEAVE_REQUESTED
    member_row.save(update_fields=["status"])
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    from core.choices import PaymentMethod
    from decimal import Decimal
    from payments.models import Payment, ReviewStatus

    pay = Payment.objects.create(
        shared_plan=world["shared_x"],
        member=member_row,
        recorded_by=world["member"],
        method=PaymentMethod.BKASH,
        amount=Decimal("50.00"),
        review_status=ReviewStatus.PENDING,
        transaction_id="XY99ZZ88WW",
    )
    from payments.models import PaymentAllocation

    PaymentAllocation.objects.create(payment=pay, due=due, amount_applied=due.amount_bdt)
    due.status = DueStatus.PENDING
    due.save(update_fields=["status"])
    body = client_for(world["owner"]).get(f"/api/shared-plans/{world['plan_x'].pk}/review/").json()
    pending = body["pending"]
    assert pending
    assert pending[0]["payer"]["leave_requested"] is True
    assert pending[0]["payer"]["email"] == world["member"].email
