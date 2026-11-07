from django.contrib import admin

from plans.models import ExchangeRate, PriceChange, Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("plan_name", "owner", "status", "plan_mode", "currency", "archived_on")
    list_filter = ("status", "plan_mode", "currency", "renewal_type")
    search_fields = ("plan_name", "owner__email")
    raw_id_fields = ("owner", "service_name", "category")


@admin.register(PriceChange)
class PriceChangeAdmin(admin.ModelAdmin):
    list_display = ("subscription", "amount", "currency", "effective_from")
    list_filter = ("currency",)
    search_fields = ("subscription__plan_name",)
    raw_id_fields = ("subscription",)


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ("user", "rate_date", "usd_to_bdt", "source")
    list_filter = ("source",)
    search_fields = ("user__email",)
    raw_id_fields = ("user",)
