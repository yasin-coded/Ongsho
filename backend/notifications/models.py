from django.conf import settings
from django.db import models


class ReminderKind(models.TextChoices):
    RENEWAL = "renewal", "Renewal"
    TRIAL_END = "trial_end", "Trial end"
    EXPIRY = "expiry", "Expiry"
    DUE_SOON = "due_soon", "Due soon"


class ReminderChannel(models.TextChoices):
    EMAIL = "email", "Email"
    IN_APP = "in_app", "In-app"


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=64)
    title = models.CharField(max_length=120, default="")
    message = models.TextField()
    payload = models.JSONField(default=dict)
    link = models.CharField(max_length=512, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "read_at", "created_at"], name="notif_user_read_created_idx"),
        ]


class Reminder(models.Model):
    subscription = models.ForeignKey(
        "plans.Subscription",
        on_delete=models.CASCADE,
        related_name="reminders",
    )
    charge = models.ForeignKey(
        "billing.Charge",
        on_delete=models.CASCADE,
        related_name="reminders",
        null=True,
        blank=True,
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reminders")
    kind = models.CharField(max_length=16, choices=ReminderKind.choices)
    target_date = models.DateField()
    days_before = models.PositiveIntegerField()
    sent_at = models.DateTimeField(null=True, blank=True)
    channel = models.CharField(max_length=16, choices=ReminderChannel.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "subscription", "target_date", "days_before", "user"],
                name="notifications_reminder_unique",
            ),
        ]
