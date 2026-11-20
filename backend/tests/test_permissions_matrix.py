"""Data-driven permission expectations across roles (architecture §8)."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient
from sharing.models import MemberStatus

from tests.test_subscriptions import WORLD_PASS, client_for
from tests.write_endpoint_matrix import WRITE_ENDPOINT_MATRIX  # re-export for hostile-input matrix

SUCCESS = frozenset({200, 201, 204})
NOT_FOUND = frozenset({404})
UNAUTHORIZED = frozenset({401})


def _request(user, method: str, path: str, **kwargs):
    client = APIClient()
    if user is not None:
        client.force_authenticate(user=user)
    return getattr(client, method.lower())(path, **kwargs)


def _expect(response, allowed: frozenset[int], *, forbid_403: bool = True):
    if forbid_403 and response.status_code == 403:
        pytest.fail(f"expected 404/401/success, got 403 for {response.request.get('PATH_INFO')}")
    assert response.status_code in allowed


@pytest.mark.django_db
@pytest.mark.parametrize(
    "method,path_template,role,expected",
    [
        ("GET", "/api/subscriptions/", "anon", UNAUTHORIZED),
        ("GET", "/api/subscriptions/", "outsider", SUCCESS),
        ("GET", "/api/subscriptions/{plan_y}/", "owner", NOT_FOUND),
        ("GET", "/api/subscriptions/{plan_x}/", "owner", SUCCESS),
        ("GET", "/api/subscriptions/{plan_x}/", "outsider", NOT_FOUND),
        ("GET", "/api/me/shared-plans/", "member", SUCCESS),
        ("GET", "/api/me/shared-plans/{plan_x}/", "member", SUCCESS),
        ("GET", "/api/me/shared-plans/{plan_x}/", "outsider", NOT_FOUND),
        ("GET", "/api/shared-plans/{plan_x}/", "owner", SUCCESS),
        ("GET", "/api/shared-plans/{plan_x}/", "member", NOT_FOUND),
        ("GET", "/api/shared-plans/{plan_x}/", "outsider", NOT_FOUND),
        ("GET", "/api/dues/", "owner", SUCCESS),
            ("GET", "/api/dues/", "member", SUCCESS),
        ("GET", "/api/notifications/", "outsider", SUCCESS),
        ("GET", "/api/dashboard/summary/", "outsider", SUCCESS),
        ("GET", "/api/calendar/", "outsider", SUCCESS),
        ("GET", "/api/charges/", "owner", SUCCESS),
            ("GET", "/api/charges/", "member", SUCCESS),
        ("GET", "/api/me/", "anon", UNAUTHORIZED),
        ("GET", "/api/me/", "member", SUCCESS),
        ("GET", "/api/me/shared-plans/{plan_x}/", "left", NOT_FOUND),
            ("GET", "/api/subscriptions/{plan_y}/", "dual", NOT_FOUND),
            ("GET", "/api/me/shared-plans/{plan_y}/", "dual", SUCCESS),
        ],
    )
def test_permissions_matrix(method, path_template, role, expected, world):
    ctx = world
    if role == "left":
        row = world["member_row"]
        row.status = MemberStatus.LEFT
        row.save(update_fields=["status"])
    plan_x = ctx["plan_x"].pk
    plan_y = ctx["plan_y"].pk
    path = path_template.format(plan_x=plan_x, plan_y=plan_y)
    user = {
        "anon": None,
        "outsider": ctx["outsider"],
        "owner": ctx["owner"],
        "member": ctx["member"],
        "left": ctx["member"],
        "dual": ctx["owner"],
    }[role]
    response = _request(user, method, path)
    _expect(response, expected)