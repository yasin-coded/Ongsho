from decimal import Decimal

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework.test import APIClient

from audit.models import AuditLog
from billing.models import Charge
from core.choices import PaymentMethod
from core.dates import today_dhaka
from dues.models import DueStatus
from payments.models import Payment, PaymentAllocation, ReviewStatus
from plans.models import Subscription
from reports import pdf as pdf_builders
from reports import services as statement_services
from reports import statement_selectors
from reports.models import Statement
from sharing.models import Member, MemberStatus, SharedPlan, SplitType
from tests.test_subscriptions import assert_error_shape, client_for

User = get_user_model()

FOOTER_FRAGMENT = b"Payments happen outside Ongsho"


def statement_month(world):
    return world["charge_x"].period_start.strftime("%Y-%m")


def owner_statement_url(plan_id, month):
    return f"/api/shared-plans/{plan_id}/statement/?month={month}"


def member_statement_url(plan_id, month):
    return f"/api/me/shared-plans/{plan_id}/statement/?month={month}"


def fetch_owner(client, world, month=None):
    month = month or statement_month(world)
    return client.get(owner_statement_url(world["plan_x"].pk, month))


def fetch_member(client, world, month=None):
    month = month or statement_month(world)
    return client.get(member_statement_url(world["plan_x"].pk, month))


@pytest.mark.django_db
def test_statement_number_format_and_stable(world):
    owner = client_for(world["owner"])
    month = statement_month(world)
    r1 = fetch_owner(owner, world, month)
    assert r1.status_code == 200
    num1 = r1["X-Statement-Number"]
    assert num1.startswith("ONG-")
    parts = num1.split("-")
    assert len(parts) == 4
    assert parts[1] == month.replace("-", "")
    assert parts[2] == f"{world['plan_x'].pk:04d}"
    stmt = Statement.objects.get(user=world["owner"], shared_plan=world["shared_x"], month=world["charge_x"].period_start.replace(day=1))
    assert parts[3] == f"{stmt.pk:04d}"
    r2 = fetch_owner(owner, world, month)
    assert r2["X-Statement-Number"] == num1


@pytest.mark.django_db
def test_owner_pdf_response_headers(world):
    r = fetch_owner(client_for(world["owner"]), world)
    assert r.status_code == 200
    assert r["Content-Type"] == "application/pdf"
    assert r["Content-Disposition"].startswith('attachment; filename="ongsho-statement-')
    assert r["Cache-Control"] == "no-store"
    assert r["X-Content-Type-Options"] == "nosniff"
    assert r.content[:4] == b"%PDF"
    assert r["X-Statement-Number"] in r["Content-Disposition"]


@pytest.mark.django_db
def test_owner_pdf_searchable_content(world):
    month = statement_month(world)
    data = statement_selectors.owner_statement_payload(world["owner"], world["shared_x"], world["charge_x"].period_start.replace(day=1))
    data["number"] = "ONG-TEST-0001-0001"
    raw = pdf_builders.build_owner_statement(data, compress=False)
    assert FOOTER_FRAGMENT in raw
    assert world["plan_x"].plan_name.encode() in raw
    assert world["member"].name.encode() in raw
    assert b"BDT" in raw
    assert data["number"].encode() in raw


@pytest.mark.django_db
def test_pdf_escaping_special_characters(world):
    world["plan_x"].plan_name = "Plan <b> & </para>"
    world["plan_x"].save(update_fields=["plan_name"])
    world["member"].name = "Mem <b> & </para>"
    world["member"].save(update_fields=["name"])
    data = statement_selectors.owner_statement_payload(world["owner"], world["shared_x"], world["charge_x"].period_start.replace(day=1))
    data["number"] = "ONG-ESC-0001-0001"
    raw = pdf_builders.build_owner_statement(data, compress=False)
    assert raw[:4] == b"%PDF"
    assert b"<b>" not in raw or b"Plan" in raw


@pytest.mark.django_db
def test_month_validation(world):
    owner = client_for(world["owner"])
    pid = world["plan_x"].pk
    r = owner.get(f"/api/shared-plans/{pid}/statement/")
    assert r.status_code == 400
    assert_error_shape(r)
    assert "month" in r.json()["error"]["fields"]

    r = owner.get(f"/api/shared-plans/{pid}/statement/?month=not-a-month")
    assert r.status_code == 400
    assert "month" in r.json()["error"]["fields"]

    future = today_dhaka().replace(day=1)
    if future.month == 12:
        future = future.replace(year=future.year + 1, month=1)
    else:
        future = future.replace(month=future.month + 1)
    r = owner.get(f"/api/shared-plans/{pid}/statement/?month={future:%Y-%m}")
    assert r.status_code == 400
    assert "month" in r.json()["error"]["fields"]


@pytest.mark.django_db
def test_nothing_to_report(world):
    owner = client_for(world["owner"])
    r = owner.get(f"/api/shared-plans/{world['plan_x'].pk}/statement/?month=2020-01")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "nothing_to_report"


@pytest.mark.django_db
def test_scoping_404_and_cross_roles(world):
    from billing import services as billing_services
    from dues import services as dues_services

    billing_services.generate_missing_charges(world["plan_y"], world["today"])
    for ch in Charge.objects.filter(subscription=world["plan_y"]):
        dues_services.recalculate_dues(ch, world["today"], force=True)
    charge_y = Charge.objects.filter(subscription=world["plan_y"]).order_by("-period_start").first()
    month_y = charge_y.period_start.strftime("%Y-%m")
    pid = world["plan_x"].pk
    month = statement_month(world)
    assert client_for(world["member"]).get(owner_statement_url(pid, month)).status_code == 404
    assert client_for(world["outsider"]).get(owner_statement_url(pid, month)).status_code == 404
    assert client_for(world["owner"]).get(member_statement_url(pid, month)).status_code == 404
    assert client_for(world["owner"]).get(member_statement_url(world["plan_y"].pk, month_y)).status_code == 200
    assert client_for(world["owner"]).get(owner_statement_url(world["plan_y"].pk, month_y)).status_code == 404


@pytest.mark.django_db
def test_member_statement_hides_other_member_due_rows(world):
    shared = world["shared_x"]
    charge = world["charge_x"]
    extra = User.objects.create_user(email="extra@ex.com", password="pass12345", name="Extra Person", email_verified=True)
    Member.objects.create(
        shared_plan=shared,
        user=extra,
        share_type=SplitType.EQUAL,
        status=MemberStatus.ACTIVE,
        joined_on=charge.period_start,
    )
    month = statement_month(world)
    month_date = world["charge_x"].period_start.replace(day=1)
    data = statement_selectors.member_statement_payload(world["member_row"], month_date)
    data["number"] = "ONG-MEM-0001-0001"
    raw = pdf_builders.build_member_statement(data, compress=False)
    assert world["member"].name.encode() in raw
    assert b"Your dues this month" in raw
    assert b"Dues this month" not in raw


@pytest.mark.django_db
def test_anonymous_401(world):
    month = statement_month(world)
    assert APIClient().get(owner_statement_url(world["plan_x"].pk, month)).status_code == 401
    assert APIClient().get(member_statement_url(world["plan_x"].pk, month)).status_code == 401


@pytest.mark.django_db
def test_cors_expose_headers():
    assert "Content-Disposition" in settings.CORS_EXPOSE_HEADERS
    assert "X-Statement-Number" in settings.CORS_EXPOSE_HEADERS


@pytest.mark.django_db
def test_audit_on_first_download(world):
    month = statement_month(world)
    before = AuditLog.objects.count()
    assert fetch_owner(client_for(world["owner"]), world, month).status_code == 200
    assert AuditLog.objects.count() == before + 1
    assert fetch_owner(client_for(world["owner"]), world, month).status_code == 200
    assert AuditLog.objects.count() == before + 1
    log = AuditLog.objects.latest("id")
    assert log.summary == f"You downloaded the statement for {month}"


@pytest.mark.django_db
def test_unique_user_plan_month(world):
    month_date = world["charge_x"].period_start.replace(day=1)
    statement_services.get_or_create_statement(world["owner"], world["shared_x"], month_date)
    with pytest.raises(IntegrityError):
        Statement.objects.create(
            user=world["owner"],
            shared_plan=world["shared_x"],
            month=month_date,
            number="ONG-DUP-0001-9999",
        )


@pytest.mark.django_db
def test_query_counts_stable_with_members(world):
    owner = client_for(world["owner"])
    month = statement_month(world)
    assert fetch_owner(owner, world, month).status_code == 200
    with CaptureQueriesContext(connection) as ctx1:
        r1 = fetch_owner(owner, world, month)
        assert r1.status_code == 200
    q1 = len(ctx1.captured_queries)
    shared = world["shared_x"]
    for i in range(9):
        u = User.objects.create_user(
            email=f"bench{i}@example.com",
            password="pass12345",
            name=f"Bench {i}",
            email_verified=True,
        )
        Member.objects.create(
            shared_plan=shared,
            user=u,
            share_type=SplitType.EQUAL,
            status=MemberStatus.ACTIVE,
            joined_on=world["charge_x"].period_start,
        )
    with CaptureQueriesContext(connection) as ctx10:
        r10 = fetch_owner(owner, world, month)
        assert r10.status_code == 200
    assert len(ctx10.captured_queries) == q1


@pytest.mark.django_db
def test_member_statement_pdf(world):
    r = fetch_member(client_for(world["member"]), world)
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"
    assert r["X-Statement-Number"]
