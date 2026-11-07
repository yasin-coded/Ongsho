from django.db import models
from django.db.models import Q


class DueStatus(models.TextChoices):
    DUE = "due", "Due"
    PENDING = "pending", "Pending"
    PAID = "paid", "Paid"
    WAIVED = "waived", "Waived"


class Due(models.Model):
    charge = models.ForeignKey("billing.Charge", on_delete=models.CASCADE, related_name="dues")
    member = models.ForeignKey("sharing.Member", on_delete=models.CASCADE, related_name="dues")
    amount_bdt = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=16, choices=DueStatus.choices)
    waiver_note = models.TextField(blank=True, default="")
    rejection_reason = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["charge", "member"], name="dues_due_charge_member_unique"),
            models.CheckConstraint(condition=Q(amount_bdt__gt=0), name="dues_due_amount_positive"),
        ]

    def __str__(self) -> str:
        return f"Due {self.id} ({self.status})"
