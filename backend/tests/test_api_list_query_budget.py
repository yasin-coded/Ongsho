from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from tests.test_subscriptions import client_for


@pytest.mark.django_db
def test_subscriptions_list_query_budget(world_rich):
    owner = client_for(world_rich["owner"])
    with CaptureQueriesContext(connection) as ctx:
        r = owner.get("/api/subscriptions/")
        assert r.status_code == 200
    assert len(ctx.captured_queries) <= 40