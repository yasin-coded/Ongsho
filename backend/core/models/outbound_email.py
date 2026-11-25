"""
Outbound email queue (transactional outbox).

Delivery semantics (worker stage): bounded at-least-once *attempts* toward the provider.
Successful inbox delivery is not guaranteed; duplicate provider submits are possible after
worker crash post-acceptance. Retries stop at OUTBOUND_EMAIL_MAX_ATTEMPTS unless permanently failed.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class OutboundEmailType(models.TextChoices):
    ACCOUNT_VERIFY = "account_verify", "Account verification"
    VERIFY_RESEND = "verify_resend", "Resend verification"
    PASSWORD_RESET = "password_reset", "Password reset"
    EMAIL_CHANGE = "email_change", "Email change verification"
    PLAN_INVITE = "plan_invite", "Plan invitation"
    REMINDER = "reminder", "Due or renewal reminder"
    PAYMENT_RECEIPT = "payment_receipt", "Payment receipt"
    PAYMENT_REJECTED = "payment_rejected", "Payment rejected"
    PASSWORD_CHANGED = "password_changed", "Password changed"
    PASSWORD_RESET_COMPLETED = "password_reset_completed", "Password reset completed"
    EMAIL_CHANGED_NEW = "email_changed_new", "Email changed (new address)"
    EMAIL_CHANGED_PREVIOUS = "email_changed_previous", "Email changed (previous address)"


class OutboundEmailStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    RETRY = "retry", "Retry"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


_ACTIVE_DELIVERY_STATUSES = (
    OutboundEmailStatus.PENDING,
    OutboundEmailStatus.PROCESSING,
    OutboundEmailStatus.RETRY,
)


class OutboundEmail(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    business_event_id = models.CharField(max_length=160, unique=True)

    email_type = models.CharField(max_length=32, choices=OutboundEmailType.choices)
    status = models.CharField(
        max_length=16,
        choices=OutboundEmailStatus.choices,
        default=OutboundEmailStatus.PENDING,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outbound_emails",
    )
    invite = models.ForeignKey(
        "sharing.Invite",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outbound_emails",
    )
    reminder = models.ForeignKey(
        "notifications.Reminder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outbound_emails",
    )

    to_email = models.EmailField()

    payload = models.JSONField(default=dict, blank=True)

    delivery_ciphertext = models.BinaryField(null=True, blank=True)
    delivery_key_version = models.PositiveSmallIntegerField(null=True, blank=True)

    attempt_count = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)

    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.CharField(max_length=64, blank=True, default="")

    sent_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["status", "next_attempt_at", "created_at"],
                name="core_outboundemail_claim_idx",
            ),
            models.Index(fields=["email_type", "created_at"], name="core_outboundemail_type_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~Q(email_type=OutboundEmailType.PLAN_INVITE) | Q(invite__isnull=False),
                name="core_outboundemail_plan_invite_requires_invite",
            ),
            models.CheckConstraint(
                condition=~Q(email_type=OutboundEmailType.REMINDER) | Q(reminder__isnull=False),
                name="core_outboundemail_reminder_requires_reminder",
            ),
            models.UniqueConstraint(
                fields=["invite"],
                condition=Q(
                    email_type=OutboundEmailType.PLAN_INVITE,
                    status__in=_ACTIVE_DELIVERY_STATUSES,
                ),
                name="core_outboundemail_one_active_invite",
            ),
            models.UniqueConstraint(
                fields=["reminder"],
                condition=Q(
                    email_type=OutboundEmailType.REMINDER,
                    status__in=_ACTIVE_DELIVERY_STATUSES,
                ),
                name="core_outboundemail_one_active_reminder",
            ),
        ]

    def __str__(self) -> str:
        return f"OutboundEmail<{self.email_type}:{self.status}:{self.id}>"