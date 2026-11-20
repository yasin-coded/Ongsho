from django.db.models.signals import pre_delete
from django.dispatch import receiver

from notifications.models import Reminder


@receiver(pre_delete, sender=Reminder)
def purge_outbox_before_reminder_delete(sender, instance, **kwargs):
    """Remove outbox rows before SET_NULL would violate reminder FK integrity checks."""
    from core.models.outbound_email import OutboundEmail, OutboundEmailType

    OutboundEmail.objects.filter(
        reminder_id=instance.pk,
        email_type=OutboundEmailType.REMINDER,
    ).delete()