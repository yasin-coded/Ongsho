import pytest

from sharing.models import SplitType

from tests.test_subscriptions import client_for


@pytest.mark.django_db
def test_equal_split_update(world):
    r = client_for(world["owner"]).put(
        f"/api/shared-plans/{world['plan_x'].pk}/split/",
        {"split_type": "equal"},
        format="json",
    )
    assert r.status_code == 200
    world["shared_x"].refresh_from_db()
    assert world["shared_x"].split_type == SplitType.EQUAL


@pytest.mark.django_db
def test_custom_split_wrong_sum(world):
    members = list(world["shared_x"].members.exclude(status="left"))
    shares = {str(m.pk): "10.00" for m in members}
    r = client_for(world["owner"]).put(
        f"/api/shared-plans/{world['plan_x'].pk}/split/",
        {"split_type": "custom", "shares": shares},
        format="json",
    )
    assert r.status_code == 400
    assert "shares" in r.json()["error"]["fields"]
