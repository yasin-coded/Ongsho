import pytest

from core.exceptions import ConflictError
from dues.models import DueStatus
from dues.state import transition


@pytest.mark.django_db
@pytest.mark.parametrize(
    "src,dst",
    [
        (DueStatus.DUE, DueStatus.PENDING),
        (DueStatus.DUE, DueStatus.PAID),
        (DueStatus.DUE, DueStatus.WAIVED),
        (DueStatus.PENDING, DueStatus.PAID),
        (DueStatus.PENDING, DueStatus.DUE),
        (DueStatus.PENDING, DueStatus.WAIVED),
        (DueStatus.PAID, DueStatus.DUE),
        (DueStatus.WAIVED, DueStatus.DUE),
    ],
)
def test_transition_allowed(world, src, dst):
    due = world["due_x"]
    due.status = src
    due.save(update_fields=["status"])
    transition(due, dst, world["owner"])
    due.refresh_from_db()
    assert due.status == dst


@pytest.mark.django_db
@pytest.mark.parametrize(
    "src,dst",
    [
        (DueStatus.PAID, DueStatus.PAID),
        (DueStatus.WAIVED, DueStatus.PAID),
        (DueStatus.DUE, DueStatus.DUE),
    ],
)
def test_transition_forbidden(world, src, dst):
    due = world["due_x"]
    due.status = src
    due.save(update_fields=["status"])
    with pytest.raises(ConflictError) as exc:
        transition(due, dst, world["owner"])
    assert exc.value.code == "invalid_due_status"
