"""Member-facing due rows and owner review field enrichment."""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

from billing.models import Charge
from core.choices import PaymentMethod
from dues.models import Due, DueStatus
from sharing.models import Member, MemberStatus, SplitType
from tests.test_payment_decisions import _submit
from tests.test_subscriptions import client_for

User = get_user_model()

DUE_ENRICHMENT_KEYS = frozenset(
    {"method", "transaction_id", "waiver_note", "rejection_reason", "payment_id"}
)


def _assert_enrichment(row):
    assert DUE_ENRICHMENT_KEYS <= set(row.keys())


def _me_detail(member_client, plan_id):
    r = member_client.get(f"/api/me/shared-plans/{plan_id}/")
    assert r.status_code == 200
    return r.json()


@pytest.mark.django_db
def test_me_history_paid_includes_payment_fields(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    member = client_for(world["member"])
    owner = client_for(world["owner"])
    pay_id = _submit(member, world["plan_x"].pk, due.pk, tid="ENRICH01").json()["payment_id"]
    assert owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json").status_code == 200
    body = _me_detail(member, world["plan_x"].pk)
    hist = next(h for h in body["history"] if h["due_id"] == due.pk)
    _assert_enrichment(hist)
    assert hist["status"] == DueStatus.PAID
    assert hist["payment_id"] == pay_id
    assert hist["method"] == PaymentMethod.BKASH
    assert hist["transaction_id"] == "ENRICH01"
    assert hist["waiver_note"] is None
    assert hist["rejection_reason"] is None


@pytest.mark.django_db
def test_me_history_waived_includes_waiver_note(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.waiver_note = ""
    due.save(update_fields=["status", "waiver_note"])
    owner = client_for(world["owner"])
    assert (
        owner.post(f"/api/dues/{due.pk}/waive/", {"note": "Birthday month"}, format="json").status_code
        == 200
    )
    due.refresh_from_db()
    assert due.status == DueStatus.WAIVED
    body = _me_detail(client_for(world["member"]), world["plan_x"].pk)
    hist = next(h for h in body["history"] if h["due_id"] == due.pk)
    _assert_enrichment(hist)
    assert hist["waiver_note"] == "Birthday month"
    assert hist["payment_id"] is None


@pytest.mark.django_db
def test_me_open_due_rejected_includes_reason(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.rejection_reason = ""
    due.save(update_fields=["status", "rejection_reason"])
    member = client_for(world["member"])
    owner = client_for(world["owner"])
    pay_id = _submit(member, world["plan_x"].pk, due.pk, tid="REJENRICH").json()["payment_id"]
    assert (
        owner.post(f"/api/payments/{pay_id}/reject/", {"reason": "ID mismatch"}, format="json").status_code
        == 200
    )
    due.refresh_from_db()
    assert due.status == DueStatus.DUE
    assert due.rejection_reason == "ID mismatch"
    body = _me_detail(member, world["plan_x"].pk)
    row = next(d for d in body["open_dues"] if d["due_id"] == due.pk)
    _assert_enrichment(row)
    assert row["rejection_reason"] == "ID mismatch"
    assert row["payment_id"] is None


@pytest.mark.django_db
def test_me_history_owner_recorded_mark_paid(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    owner = client_for(world["owner"])
    r = owner.post(
        f"/api/dues/{due.pk}/mark-paid/",
        {"date": str(world["today"]), "method": PaymentMethod.CASH, "note": "cash"},
        format="json",
    )
    assert r.status_code == 200
    body = _me_detail(client_for(world["member"]), world["plan_x"].pk)
    hist = next(h for h in body["history"] if h["due_id"] == due.pk)
    _assert_enrichment(hist)
    assert hist["method"] == PaymentMethod.CASH
    assert hist["payment_id"] is not None


@pytest.mark.django_db
def test_me_history_covered_by_another_member_payment(world):
    shared = world["shared_x"]
    charge = world["charge_x"]
    victim_user = User.objects.create_user(
        email="covervictim@example.com", password="pass12345", name="Victim", email_verified=True
    )
    other = Member.objects.create(
        shared_plan=shared,
        user=victim_user,
        share_type=SplitType.EQUAL,
        status=MemberStatus.ACTIVE,
        joined_on=world["plan_x"].start_date,
    )
    from dues import services as dues_services

    dues_services.recalculate_dues(charge, world["today"], force=True)
    assert client_for(victim_user).get(f"/api/me/shared-plans/{world['plan_x'].pk}/").status_code == 200
    due_other = Due.objects.get(charge=charge, member=other)
    due_other.status = DueStatus.DUE
    due_other.save(update_fields=["status"])
    member = client_for(world["member"])
    owner = client_for(world["owner"])
    pay_id = member.post(
        "/api/payments/",
        {
            "plan_id": world["plan_x"].pk,
            "due_ids": [due_other.pk],
            "method": PaymentMethod.BKASH,
            "transaction_id": "COVEROTHER",
        },
        format="json",
    ).json()["payment_id"]
    assert owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json").status_code == 200
    victim_client = client_for(other.user)
    body = _me_detail(victim_client, world["plan_x"].pk)
    hist = next(h for h in body["history"] if h["due_id"] == due_other.pk)
    _assert_enrichment(hist)
    assert hist["payment_id"] == pay_id
    assert hist["transaction_id"] == "COVEROTHER"


@pytest.mark.django_db
def test_review_decided_member_is_owner_seat(world):
    shared = world["shared_x"]
    owner = world["owner"]
    if not Member.objects.filter(shared_plan=shared, user=owner).exists():
        Member.objects.create(
            shared_plan=shared,
            user=owner,
            share_type=SplitType.EQUAL,
            status=MemberStatus.ACTIVE,
            joined_on=world["plan_x"].start_date,
        )
        from dues import services as dues_services

        dues_services.recalculate_dues(world["charge_x"], world["today"], force=True)
    owner_due = Due.objects.get(charge=world["charge_x"], member__user=owner)
    owner_due.status = DueStatus.DUE
    owner_due.save(update_fields=["status"])
    owner_client = client_for(owner)
    assert (
        owner_client.post(
            f"/api/dues/{owner_due.pk}/mark-paid/",
            {"date": str(world["today"]), "method": PaymentMethod.CASH},
            format="json",
        ).status_code
        == 200
    )
    body = owner_client.get(f"/api/shared-plans/{world['plan_x'].pk}/review/").json()
    decided = next(d for d in body["decided"] if d["due_id"] == owner_due.pk)
    assert decided["member"]["is_owner_seat"] is True


@pytest.mark.django_db
def test_review_pending_covers_member_id_and_is_payer(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    pay_id = _submit(client_for(world["member"]), world["plan_x"].pk, due.pk, tid="COVSELF").json()["payment_id"]
    body = client_for(world["owner"]).get(f"/api/shared-plans/{world['plan_x'].pk}/review/").json()
    pend = next(p for p in body["pending"] if p["payment_id"] == pay_id)
    cover = pend["covers"][0]
    assert cover["member_id"] == world["member_row"].pk
    assert cover["is_payer"] is True

    shared = world["shared_x"]
    other = Member.objects.filter(shared_plan=shared).exclude(pk=world["member_row"].pk).first()
    due_other = Due.objects.get(charge=world["charge_x"], member=other)
    due_other.status = DueStatus.DUE
    due_other.save(update_fields=["status"])
    iou_id = client_for(world["member"]).post(
        "/api/payments/",
        {
            "plan_id": world["plan_x"].pk,
            "due_ids": [due_other.pk],
            "method": PaymentMethod.BKASH,
            "transaction_id": "COVOTHER",
        },
        format="json",
    ).json()["payment_id"]
    body2 = client_for(world["owner"]).get(f"/api/shared-plans/{world['plan_x'].pk}/review/").json()
    iou = next(p for p in body2["pending"] if p["payment_id"] == iou_id)
    cover2 = iou["covers"][0]
    assert cover2["member_id"] == other.pk
    assert cover2["is_payer"] is False


@pytest.mark.django_db
def test_owner_member_detail_rows_enriched(world):
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    member = client_for(world["member"])
    pay_id = _submit(member, world["plan_x"].pk, due.pk, tid="MEMDET01").json()["payment_id"]
    assert client_for(world["owner"]).post(f"/api/payments/{pay_id}/confirm/", {}, format="json").status_code == 200
    r = client_for(world["owner"]).get(f"/api/members/{world['member_row'].pk}/")
    assert r.status_code == 200
    rows = r.json()["rows"]
    row = next(x for x in rows if x["due_id"] == due.pk)
    _assert_enrichment(row)
    assert row["payment_id"] == pay_id


@pytest.mark.django_db
def test_me_shared_detail_privacy_no_foreign_payment_status(world):
    body = _me_detail(client_for(world["member"]), world["plan_x"].pk)
    raw = json.dumps(body)
    assert world["owner"].email not in raw
    for m in body["members"]:
        assert "email" not in m
        assert "due_status" not in m
        if not m.get("is_you"):
            assert m.get("status") is None
    assert all(r["due_id"] for r in body["history"])
    assert all("status" in r for r in body["open_dues"] + body["history"])


@pytest.mark.django_db
def test_me_shared_detail_query_count_constant_with_members(world):
    client = client_for(world["member"])
    pid = world["plan_x"].pk

    def count_queries():
        with CaptureQueriesContext(connection) as ctx:
            r = client.get(f"/api/me/shared-plans/{pid}/")
            assert r.status_code == 200
        return len(ctx)

    base = count_queries()
    assert count_queries() == base
    for i in range(8):
        u = User.objects.create_user(
            email=f"dueen{i}@example.com",
            password="pass12345",
            name=f"Extra {i}",
            email_verified=True,
        )
        Member.objects.create(
            shared_plan=world["shared_x"],
            user=u,
            share_type=SplitType.EQUAL,
            status=MemberStatus.ACTIVE,
            joined_on=world["plan_x"].start_date,
        )
    from dues import services as dues_services

    for ch in Charge.objects.filter(subscription=world["plan_x"]):
        dues_services.recalculate_dues(ch, world["today"], force=True)
    assert count_queries() == base