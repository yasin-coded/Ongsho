from django.conf import settings
from django.db import models


class Statement(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="statements")
    shared_plan = models.ForeignKey("sharing.SharedPlan", on_delete=models.CASCADE, related_name="statements")
    number = models.CharField(max_length=64, unique=True)
    month = models.DateField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "shared_plan", "month"],
                name="reports_statement_user_plan_month_unique",
            ),
        ]
