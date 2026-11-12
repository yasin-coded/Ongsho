from django.utils import timezone

from core.exceptions import NotFound
from notifications.models import Notification


def _notification_for_user(user, notification_id: int) -> Notification:
    try:
        return Notification.objects.get(pk=notification_id, user=user)
    except Notification.DoesNotExist:
        raise NotFound("Not found.") from None


def mark_notification_read(user, notification_id: int) -> Notification:
    notification = _notification_for_user(user, notification_id)
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])
    return notification


def mark_all_notifications_read(user) -> int:
    now = timezone.now()
    return Notification.objects.filter(user=user, read_at__isnull=True).update(read_at=now)
