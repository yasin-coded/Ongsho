from __future__ import annotations

from django.dispatch import receiver

from billing import services as billing_services
from core.signals import plan_created


@receiver(plan_created)
def on_plan_created(sender, *, plan, today, **kwargs):
    billing_services.generate_missing_charges(plan, today)
