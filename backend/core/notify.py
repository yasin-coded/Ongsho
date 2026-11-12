from __future__ import annotations

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone


def notify(user, kind: str, title: str, message: str, link: str = "", payload=None):
    from notifications.kinds import validate_kind

    try:
        validate_kind(kind)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    if not title or len(title) > 120:
        raise ValidationError("Title must be 1–120 characters.")
    if payload is None:
        payload = {}
    Notification = apps.get_model("notifications", "Notification")
    return Notification.objects.create(
        user=user,
        kind=kind,
        title=title,
        message=message,
        link=link or "",
        payload=payload,
    )


def resolve_notifications(action_type: str, **ids) -> int:
    """Mark unread notifications read when their payload action matches the given ids."""
    if not ids:
        return 0
    Notification = apps.get_model("notifications", "Notification")
    query = Q(read_at__isnull=True, payload__action__type=action_type)
    for key, value in ids.items():
        query &= Q(**{f"payload__action__{key}": value})
    now = timezone.now()
    return Notification.objects.filter(query).update(read_at=now)
