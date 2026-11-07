from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from core.choices import Currency, PaymentMethod


class PlanMode(models.TextChoices):
    OWNER = "owner", "Owner"
    RESELLER = "reseller", "Reseller"


class CycleUnit(models.TextChoices):
    DAY = "day", "Day"
    WEEK = "week", "Week"
    MONTH = "month", "Month"
    YEAR = "year", "Year"


class RenewalType(models.TextChoices):
    AUTO = "auto", "Auto"
    FIXED_TERM = "fixed_term", "Fixed term"


class SubscriptionStatus(models.TextChoices):
    TRIAL = "trial", "Trial"
    ACTIVE = "active", "Active"
    PAUSED = "paused", "Paused"
    CANCELLED = "cancelled", "Cancelled"
    EXPIRED = "expired", "Expired"


class ActiveSubscriptionManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(archived_on__isnull=True)


class Subscription(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_subscriptions")
    service_name = models.ForeignKey("catalog.ServiceName", on_delete=models.PROTECT, related_name="subscriptions")
    category = models.ForeignKey("catalog.Category", on_delete=models.PROTECT, related_name="subscriptions")
    plan_name = models.CharField(max_length=255)
    plan_mode = models.CharField(max_length=16, choices=PlanMode.choices)
    note = models.TextField(blank=True, default="")
    currency = models.CharField(max_length=3, choices=Currency.choices)
    cycle_unit = models.CharField(max_length=8, choices=CycleUnit.choices)
    cycle_count = models.PositiveIntegerField()
    anchor_day = models.PositiveSmallIntegerField()
    start_date = models.DateField()
    trial_end_date = models.DateField(null=True, blank=True)
    renewal_type = models.CharField(max_length=16, choices=RenewalType.choices)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=SubscriptionStatus.choices)
    recommended_method = models.CharField(max_length=32, choices=PaymentMethod.choices)
    rarely_used = models.BooleanField(default=False)
    archived_on = models.DateTimeField(null=True, blank=True)

    objects = ActiveSubscriptionManager()
    all_with_archived = models.Manager()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(cycle_count__gte=1), name="plans_subscription_cycle_count_gte_1"),
            models.CheckConstraint(
                condition=Q(anchor_day__gte=1, anchor_day__lte=31),
                name="plans_subscription_anchor_day_range",
            ),
            models.CheckConstraint(
                condition=(Q(renewal_type=RenewalType.FIXED_TERM) & Q(end_date__isnull=False))
                | (~Q(renewal_type=RenewalType.FIXED_TERM) & Q(end_date__isnull=True)),
                name="plans_subscription_fixed_term_end_date",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            previous = Subscription.all_with_archived.filter(pk=self.pk).values("plan_mode").first()
            if previous and previous["plan_mode"] != self.plan_mode:
                raise ValidationError("plan_mode cannot change after creation.")
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.plan_name


class PriceChange(models.Model):
    subscription = models.ForeignKey("plans.Subscription", on_delete=models.CASCADE, related_name="price_changes")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, choices=Currency.choices)
    effective_from = models.DateField()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="plans_pricechange_amount_positive"),
        ]

    def __str__(self) -> str:
        return f"{self.subscription_id} @ {self.effective_from}"


class ExchangeRate(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="exchange_rates")
    rate_date = models.DateField()
    usd_to_bdt = models.DecimalField(max_digits=12, decimal_places=4)
    source = models.CharField(max_length=64, default="manual")

    def __str__(self) -> str:
        return f"{self.rate_date} {self.usd_to_bdt}"
