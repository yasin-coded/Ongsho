"""Security tests for read-only OutboundEmail admin."""

from __future__ import annotations

import uuid

import pytest
from django.contrib import admin as django_admin
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import Client
from django.urls import reverse

from core.mail_enqueue import enqueue_outbound_email
from core.models.outbound_email import OutboundEmail, OutboundEmailStatus, OutboundEmailType
from core.admin import OutboundEmailAdmin
from core.models.outbound_email import OutboundEmail as OutboundEmailModel

User = get_user_model()


def _staff_user(*, superuser: bool = False) -> User:
    suffix = "su" if superuser else "st"
    return User.objects.create_user(
        email=f"outbox-admin-{suffix}@example.com",
        password="pass12345",
        name="Staff",
        is_staff=True,
        is_superuser=superuser,
    )


def _pending_row(owner):
    with transaction.atomic():
        return enqueue_outbound_email(
            email_type=OutboundEmailType.ACCOUNT_VERIFY,
            business_event_id=f"admin:{uuid.uuid4()}",
            to_email=owner.email,
            user=owner,
        )


@pytest.fixture
def admin_row(db):
    owner = User.objects.create_user(
        email="outbox-row-owner@example.com",
        password="pass12345",
        name="Owner",
        email_verified=True,
    )
    return _pending_row(owner)


@pytest.fixture
def admin_client_staff(admin_row):
    user = _staff_user(superuser=False)
    client = Client()
    client.force_login(user)
    return client, user


@pytest.fixture
def admin_client_superuser(admin_row):
    user = _staff_user(superuser=True)
    client = Client()
    client.force_login(user)
    return client, user


@pytest.mark.django_db
def test_staff_can_view_changelist(admin_client_staff, admin_row):
    client, _ = admin_client_staff
    url = reverse("admin:core_outboundemail_changelist")
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    assert str(admin_row.pk) in content
    assert admin_row.business_event_id in content


@pytest.mark.django_db
def test_staff_can_view_detail_page(admin_client_staff, admin_row):
    client, _ = admin_client_staff
    url = reverse("admin:core_outboundemail_change", args=[admin_row.pk])
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    assert admin_row.last_error_code in content or "status" in content.lower()
    assert "outbox-row-owner@example.com" not in content
    assert "/admin/accounts/user/" not in content
    assert "/admin/sharing/invite/" not in content
    assert "/admin/notifications/reminder/" not in content
    assert str(admin_row.user_id) in content


@pytest.mark.django_db
def test_staff_cannot_add_or_delete_via_admin(admin_client_staff):
    client, _ = admin_client_staff
    add_url = reverse("admin:core_outboundemail_add")
    assert client.get(add_url).status_code == 403

    model_admin = OutboundEmailAdmin(OutboundEmailModel, django_admin.site)
    class _Req:
        user = _

    assert model_admin.has_add_permission(_Req()) is False
    assert model_admin.has_delete_permission(_Req()) is False


@pytest.mark.django_db
def test_superuser_cannot_change_add_or_delete(admin_client_superuser, admin_row):
    client, user = admin_client_superuser
    model_admin = OutboundEmailAdmin(OutboundEmailModel, django_admin.site)

    class _Req:
        pass

    req = _Req()
    req.user = user
    assert model_admin.has_view_permission(req, admin_row) is True
    assert model_admin.has_change_permission(req, admin_row) is False
    assert model_admin.has_add_permission(req) is False
    assert model_admin.has_delete_permission(req, admin_row) is False

    change_url = reverse("admin:core_outboundemail_change", args=[admin_row.pk])
    assert client.get(change_url).status_code == 200


@pytest.mark.django_db
def test_forged_post_does_not_mutate_row(admin_client_staff, admin_row):
    client, _ = admin_client_staff
    url = reverse("admin:core_outboundemail_change", args=[admin_row.pk])
    response = client.post(
        url,
        {
            "status": OutboundEmailStatus.SENT,
            "email_type": OutboundEmailType.PASSWORD_RESET,
            "business_event_id": "forged:event",
        },
    )
    assert response.status_code in (403, 405)
    admin_row.refresh_from_db()
    assert admin_row.status == OutboundEmailStatus.PENDING
    assert admin_row.email_type == OutboundEmailType.ACCOUNT_VERIFY
    assert admin_row.business_event_id != "forged:event"


@pytest.mark.django_db
def test_list_filter_and_search_still_work(admin_client_staff, admin_row):
    client, _ = admin_client_staff
    base = reverse("admin:core_outboundemail_changelist")
    filtered = client.get(base, {"status__exact": OutboundEmailStatus.PENDING})
    assert filtered.status_code == 200
    assert str(admin_row.pk) in filtered.content.decode()

    searched = client.get(base, {"q": admin_row.business_event_id})
    assert searched.status_code == 200
    assert str(admin_row.pk) in searched.content.decode()