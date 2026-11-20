"""Hostile payloads on write routes must not 500 and must not mutate data when rejected."""

from __future__ import annotations

import json
import math

import pytest
from django.conf import settings
from django.db import connection
from core.exceptions import ongsho_exception_handler
from tests.test_auth import APP_HEADER, assert_error_shape

ALLOWED = frozenset({400, 401, 403, 404, 405, 409, 410, 413, 415, 429})

TABLES = (
    "accounts_user",
    "plans_subscription",
    "billing_charge",
    "dues_due",
    "payments_payment",
    "sharing_member",
    "sharing_sharedplan",
)


def _table_counts() -> dict[str, int]:
    out = {}
    with connection.cursor() as cur:
        for t in TABLES:
            cur.execute(f'SELECT COUNT(*) FROM "{t}"')
            out[t] = cur.fetchone()[0]
    return out


def _payload_variants() -> list[tuple[str, object]]:
    big = "x" * 100_000
    huge_num = "999999999999999999999"
    return [
        ("empty", {}),
        ("wrong_types", {"email": 123, "amount": [], "seats": "two", "plan_id": {}}),
        ("nulls", {"email": None, "password": None, "plan_name": None, "due_ids": None}),
        ("big_string", {"note": big, "plan_name": big, "transaction_id": big[:120]}),
        ("oversized", {}),
        ("rtl_emoji", {"plan_name": "اختبار 🎭", "note": "مرحبا"}),
        ("nested", {"a": {"b": {"c": {"d": {"e": {"f": list(range(40))}}}}}}),
        ("sql_probe", {"plan_name": "'; DROP TABLE dues_due;--", "email": "a' OR '1'='1"}),
        ("xss_probe", {"plan_name": "<script>alert(1)</script>", "note": "<img onerror=alert(1)>"}),
        (
            "bad_ids",
            {
                "id": -1,
                "plan_id": 0,
                "due_ids": ["abc"],
                "member_id": huge_num,
                "category": "abc",
            },
        ),
        (
            "decimal_edges",
            {"amount": "-1", "rate": "0", "seats": 0, "usd_to_bdt": "-100"},
        ),
        ("nan_inf", {"amount": math.nan, "rate": math.inf, "usd_to_bdt": math.nan}),
        ("null_byte", {"plan_name": "safe\u0000bad", "transaction_id": "ok\u0000bad"}),
    ]


from tests.write_endpoint_matrix import (
    WRITE_ENDPOINT_MATRIX,
    client_for_role,
    prepare_write_route,
    resolve_write_path,
)

_REJECT_CASES = [(e.method, e.path_template, e.role) for e in WRITE_ENDPOINT_MATRIX if e.hostile_reject]
_NO_REJECT_CASES = [(e.method, e.path_template, e.role) for e in WRITE_ENDPOINT_MATRIX if not e.hostile_reject]


def _send_write(client, method: str, path: str, payload_name: str, payload: object):
    client_fn = getattr(client, method.lower())
    if payload_name == "nan_inf":
        return client_fn(
            path,
            data=json.dumps(payload, allow_nan=True),
            content_type="application/json",
            **APP_HEADER,
        )
    if payload_name == "oversized":
        size = settings.DATA_UPLOAD_MAX_MEMORY_SIZE + 50_000
        return client_fn(path, data=b"x" * size, content_type="application/json", **APP_HEADER)
    return client_fn(path, data=payload, format="json", **APP_HEADER)


@pytest.mark.django_db
@pytest.mark.parametrize("payload_name,payload", _payload_variants())
@pytest.mark.parametrize("method,path_template,role", _REJECT_CASES)
def test_write_endpoint_handles_hostile_payload(
    method, path_template, role, payload_name, payload, world
):
    endpoint = next(
        e
        for e in WRITE_ENDPOINT_MATRIX
        if e.method == method and e.path_template == path_template and e.role == role
    )
    prepare_write_route(world, endpoint)
    path = resolve_write_path(world, path_template, method=method)
    client = client_for_role(world, role)
    before = _table_counts()
    response = _send_write(client, method, path, payload_name, payload)
    assert response.status_code != 500, (
        f"{method} {path} {payload_name} -> {response.status_code} {getattr(response, 'content', b'')[:200]!r}"
    )
    assert response.status_code in ALLOWED, f"expected rejection, got {response.status_code} for {payload_name} on {path}"
    if response.status_code not in (413, 415):
        assert_error_shape(response)
    assert _table_counts() == before, f"DB mutated on rejected {method} {path} {payload_name}"


@pytest.mark.django_db
@pytest.mark.parametrize("payload_name,payload", _payload_variants())
@pytest.mark.parametrize("method,path_template,role", _NO_REJECT_CASES)
def test_write_endpoint_never_500_on_action_post(
    method, path_template, role, payload_name, payload, world
):
    """Routes that ignore or minimally parse bodies: still must not 500 on hostile input."""
    endpoint = next(
        e
        for e in WRITE_ENDPOINT_MATRIX
        if e.method == method and e.path_template == path_template and e.role == role
    )
    prepare_write_route(world, endpoint)
    path = resolve_write_path(world, path_template, method=method)
    client = client_for_role(world, role)
    response = _send_write(client, method, path, payload_name, payload)
    assert response.status_code != 500, (
        f"{method} {path} {payload_name} -> {response.status_code} {getattr(response, 'content', b'')[:200]!r}"
    )


@pytest.mark.django_db
def test_debug_off_unhandled_is_generic_json(settings):
    settings.DEBUG = False
    response = ongsho_exception_handler(RuntimeError("internal detail xyzzy"), {"request": None, "view": None})
    assert response.status_code == 500
    body = response.data
    assert body["error"]["code"] == "server_error"
    assert "xyzzy" not in body["error"]["message"]
    assert "traceback" not in json.dumps(body).lower()