from django.conf import settings
from django.db import models
from django.db.models import Q

from core.choices import PaymentMethod


class ReviewStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    REJECTED = "rejected", "Rejected"
    REVERSED = "reversed", "Reversed"


class Payment(models.Model):
    shared_plan = models.ForeignKey("sharing.SharedPlan", on_delete=models.CASCADE, related_name="payments")
    member = models.ForeignKey(
        "sharing.Member",
        on_delete=models.CASCADE,
        related_name="payments_made",
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="payments_recorded",
    )
    method = models.CharField(max_length=32, choices=PaymentMethod.choices)
    transaction_id = models.CharField(max_length=255, null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_on = models.DateField(null=True, blank=True)
    review_status = models.CharField(max_length=16, choices=ReviewStatus.choices)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="payments_payment_amount_positive"),
            models.UniqueConstraint(
                fields=["shared_plan", "transaction_id"],
                condition=Q(transaction_id__isnull=False),
                name="payments_payment_txn_per_plan_unique",
            ),
        ]


class PaymentAllocation(models.Model):
    payment = models.ForeignKey("payments.Payment", on_delete=models.CASCADE, related_name="allocations")
    due = models.ForeignKey("dues.Due", on_delete=models.CASCADE, related_name="allocations")
    amount_applied = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(amount_applied__gt=0),
                name="payments_allocation_amount_positive",
            ),
        ]
