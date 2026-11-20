"""Read-only Django admin for operational outbox inspection."""

from __future__ import annotations

from django.contrib import admin

from core.models.outbound_email import OutboundEmail


@admin.register(OutboundEmail)
class OutboundEmailAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "email_type",
        "status",
        "attempt_count",
        "last_error_code",
        "business_event_id",
        "user_id_column",
        "invite_id_column",
        "reminder_id_column",
        "created_at",
        "next_attempt_at",
        "sent_at",
    )
    list_filter = ("email_type", "status")
    search_fields = ("id", "business_event_id", "last_error_code")
    list_display_links = ("id",)

    @admin.display(description="User ID", ordering="user_id")
    def user_id_column(self, obj: OutboundEmail) -> str:
        return "" if obj.user_id is None else str(obj.user_id)

    @admin.display(description="Invite ID", ordering="invite_id")
    def invite_id_column(self, obj: OutboundEmail) -> str:
        return "" if obj.invite_id is None else str(obj.invite_id)

    @admin.display(description="Reminder ID", ordering="reminder_id")
    def reminder_id_column(self, obj: OutboundEmail) -> str:
        return "" if obj.reminder_id is None else str(obj.reminder_id)

    @admin.display(description="User ID")
    def user_id_display(self, obj: OutboundEmail) -> str:
        return "—" if obj.user_id is None else str(obj.user_id)

    @admin.display(description="Invite ID")
    def invite_id_display(self, obj: OutboundEmail) -> str:
        return "—" if obj.invite_id is None else str(obj.invite_id)

    @admin.display(description="Reminder ID")
    def reminder_id_display(self, obj: OutboundEmail) -> str:
        return "—" if obj.reminder_id is None else str(obj.reminder_id)

    _detail_readonly_fields = (
        "id",
        "idempotency_key",
        "business_event_id",
        "email_type",
        "status",
        "user_id_display",
        "invite_id_display",
        "reminder_id_display",
        "attempt_count",
        "next_attempt_at",
        "locked_at",
        "locked_by",
        "sent_at",
        "last_error_code",
        "created_at",
        "updated_at",
        "delivery_key_version",
    )

    def get_readonly_fields(self, request, obj=None):
        return self._detail_readonly_fields

    def get_fields(self, request, obj=None):
        return list(self._detail_readonly_fields)

    def has_module_permission(self, request):
        return bool(request.user and request.user.is_active and request.user.is_staff)

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["show_save"] = False
        extra_context["show_save_and_continue"] = False
        extra_context["show_delete"] = False
        return super().change_view(request, object_id, form_url, extra_context=extra_context)