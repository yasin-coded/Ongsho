from django.contrib import admin

from audit.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "action", "entity_type", "entity_id")
    list_filter = ("action", "entity_type")
    search_fields = ("action", "entity_type")
    readonly_fields = ("user", "action", "entity_type", "entity_id", "old_value", "new_value", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
