from django.contrib import admin

from billing.models import Charge


@admin.register(Charge)
class ChargeAdmin(admin.ModelAdmin):
    list_display = ("subscription", "period_start", "due_date", "amount_bdt", "status", "locked")
    list_filter = ("status", "currency", "locked")
    search_fields = ("subscription__plan_name",)
    raw_id_fields = ("subscription",)
