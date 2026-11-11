from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "billing"

    def ready(self):
        from core.signals import plan_prices_changed

        from billing import services

        def _on_prices_changed(sender, plan, **kwargs):
            from core.dates import today_dhaka

            services.refresh_unlocked_charges(plan, today_dhaka())

        plan_prices_changed.connect(_on_prices_changed, dispatch_uid="billing_refresh_unlocked")
