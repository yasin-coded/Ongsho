from django.contrib import admin

from dues.models import Due


@admin.register(Due)
class DueAdmin(admin.ModelAdmin):
    list_display = ("charge", "member", "amount_bdt", "status")
    list_filter = ("status",)
    raw_id_fields = ("charge", "member")
