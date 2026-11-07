from django.contrib import admin

from payments.models import Payment, PaymentAllocation


class PaymentAllocationInline(admin.TabularInline):
    model = PaymentAllocation
    extra = 0
    raw_id_fields = ("due",)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("shared_plan", "member", "amount", "review_status", "method")
    list_filter = ("review_status", "method")
    search_fields = ("transaction_id",)
    raw_id_fields = ("shared_plan", "member", "recorded_by")
    inlines = [PaymentAllocationInline]


@admin.register(PaymentAllocation)
class PaymentAllocationAdmin(admin.ModelAdmin):
    list_display = ("payment", "due", "amount_applied")
    raw_id_fields = ("payment", "due")
