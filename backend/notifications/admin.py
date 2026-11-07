from django.contrib import admin

from notifications.models import Notification, Reminder


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "kind", "created_at", "read_at")
    list_filter = ("kind",)
    search_fields = ("user__email", "message")
    raw_id_fields = ("user",)


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = ("user", "charge", "kind", "days_before", "send_on", "channel")
    list_filter = ("kind", "channel")
    raw_id_fields = ("charge", "user")
