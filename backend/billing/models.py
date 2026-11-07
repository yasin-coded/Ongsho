from django.db import models
from django.db.models import Q

from core.choices import Currency


class ChargeStatus(models.TextChoices):
    UPCOMING = "upcoming", "Upcoming"
    DUE = "due", "Due"
    PAID = "paid", "Paid"
    SKIPPED = "skipped", "Skipped"


class Charge(models.Model):
    subscription = models.ForeignKey("plans.Subscription", on_delete=models.CASCADE, related_name="charges")
    period_start = models.DateField()
    period_end = models.DateField()
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, choices=Currency.choices)
    rate_used = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    amount_bdt = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=16, choices=ChargeStatus.choices)
    locked = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "period_start"],
                name="billing_charge_subscription_period_unique",
            ),
            models.CheckConstraint(condition=Q(amount__gt=0), name="billing_charge_amount_positive"),
            models.CheckConstraint(condition=Q(amount_bdt__gt=0), name="billing_charge_amount_bdt_positive"),
        ]

    def __str__(self) -> str:
        return f"{self.subscription_id} {self.period_start}"
