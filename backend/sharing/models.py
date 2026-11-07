from django.conf import settings
from django.db import models
from django.db.models import Q


class SplitType(models.TextChoices):
    EQUAL = "equal", "Equal"
    CUSTOM = "custom", "Custom"


class MemberStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    LEAVE_REQUESTED = "leave_requested", "Leave requested"
    LEFT = "left", "Left"


class InviteStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    DECLINED = "declined", "Declined"
    CANCELLED = "cancelled", "Cancelled"


class TransferStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    DECLINED = "declined", "Declined"
    CANCELLED = "cancelled", "Cancelled"


class SharedPlan(models.Model):
    subscription = models.OneToOneField(
        "plans.Subscription",
        on_delete=models.CASCADE,
        related_name="shared_plan",
    )
    split_type = models.CharField(max_length=16, choices=SplitType.choices)

    def __str__(self) -> str:
        return f"Shared {self.subscription_id}"


class Member(models.Model):
    shared_plan = models.ForeignKey("sharing.SharedPlan", on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="memberships")
    share_type = models.CharField(max_length=16, choices=SplitType.choices)
    share_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=MemberStatus.choices)
    joined_on = models.DateField()
    left_on = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["shared_plan", "user"],
                name="sharing_member_shared_plan_user_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} in {self.shared_plan_id}"


class Invite(models.Model):
    shared_plan = models.ForeignKey("sharing.SharedPlan", on_delete=models.CASCADE, related_name="invites")
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="invites_sent",
    )
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invites_accepted",
    )
    email = models.EmailField()
    token_hash = models.CharField(max_length=128, unique=True)
    expires_on = models.DateTimeField()
    status = models.CharField(max_length=16, choices=InviteStatus.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["shared_plan", "email"],
                condition=Q(status=InviteStatus.PENDING),
                name="sharing_invite_pending_per_email",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.lower()
        super().save(*args, **kwargs)


class OwnershipTransfer(models.Model):
    shared_plan = models.ForeignKey("sharing.SharedPlan", on_delete=models.CASCADE, related_name="transfers")
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="transfers_from",
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="transfers_to",
    )
    status = models.CharField(max_length=16, choices=TransferStatus.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["shared_plan"],
                condition=Q(status=TransferStatus.PENDING),
                name="sharing_transfer_one_pending_per_plan",
            ),
            models.CheckConstraint(
                condition=~Q(from_user=models.F("to_user")),
                name="sharing_transfer_distinct_users",
            ),
        ]
