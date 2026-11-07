from django.conf import settings
from django.db import models


class ReminderKind(models.TextChoices):
    RENEWAL = "renewal", "Renewal"
    TRIAL_END = "trial_end", "Trial end"
    EXPIRY = "expiry", "Expiry"


class ReminderChannel(models.TextChoices):
    EMAIL = "email", "Email"
    IN_APP = "in_app", "In-app"


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=64)
    message = models.TextField()
    link = models.CharField(max_length=512, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "read_at", "created_at"], name="notif_user_read_created_idx"),
        ]


class Reminder(models.Model):
    charge = models.ForeignKey("billing.Charge", on_delete=models.CASCADE, related_name="reminders")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reminders")
    kind = models.CharField(max_length=16, choices=ReminderKind.choices)
    days_before = models.PositiveIntegerField()
    send_on = models.DateField()
    sent_at = models.DateTimeField(null=True, blank=True)
    channel = models.CharField(max_length=16, choices=ReminderChannel.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "charge", "days_before", "user"],
                name="notifications_reminder_unique",
            ),
        ]
