"""Owner subscription list pagination and global totals (Stage 5.6)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from plans.models import Subscription
from tests.test_subscriptions import WORLD_PASS, client_for, plan_payload

User = get_user_model()


@pytest.fixture
def owner_paginated(db):
    from tests.helpers import ensure_catalog_presets

    ensure_catalog_presets()
    owner = User.objects.create_user(
        email="pagowner@example.com",
        password=WORLD_PASS,
        name="Pag Owner",
        email_verified=True,
    )
    client = client_for(owner)
    for i in range(25):
        r = client.post(
            "/api/subscriptions/",
            {**plan_payload(plan_name=f"Pag Plan {i:02d}"), "seats": 2},
            format="json",
        )
        assert r.status_code == 201, r.content
    return owner


@pytest.mark.django_db
def test_unfiltered_pagination_pages_and_global_totals(owner_paginated):
    owner = owner_paginated
    client = client_for(owner)
    expected_count = Subscription.objects.filter(owner=owner).count()
    assert expected_count >= 25

    baseline = client.get("/api/subscriptions/").json()
    totals_ref = baseline["totals"]

    r1 = client.get("/api/subscriptions/?page=1&page_size=10")
    r2 = client.get("/api/subscriptions/?page=2&page_size=10")
    assert r1.status_code == 200
    assert r2.status_code == 200
    page1 = r1.json()
    page2 = r2.json()

    assert page1["count"] == expected_count
    assert page2["count"] == expected_count
    assert len(page1["results"]) <= 10
    assert len(page2["results"]) <= 10
    assert len(page1["results"]) == 10
    assert len(page2["results"]) == 10

    ids1 = {r["id"] for r in page1["results"]}
    ids2 = {r["id"] for r in page2["results"]}
    assert not ids1 & ids2

    assert page1["totals"] == totals_ref
    assert page2["totals"] == totals_ref


@pytest.mark.django_db
def test_filtered_list_subset_preserves_global_totals(owner_paginated):
    owner = owner_paginated
    client = client_for(owner)
    flagged = Subscription.objects.filter(owner=owner).order_by("id").first()
    assert flagged is not None
    flagged.rarely_used = True
    flagged.save(update_fields=["rarely_used"])

    unfiltered = client.get("/api/subscriptions/").json()
    filtered = client.get("/api/subscriptions/?rarely_used=true").json()

    assert filtered["count"] < unfiltered["count"]
    assert len(filtered["results"]) <= filtered["count"]
    assert any(r["id"] == flagged.pk for r in filtered["results"])

    assert filtered["totals"] == unfiltered["totals"]