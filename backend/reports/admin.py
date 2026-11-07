from django.contrib import admin

from reports.models import Statement


@admin.register(Statement)
class StatementAdmin(admin.ModelAdmin):
    list_display = ("number", "user", "shared_plan", "month")
    search_fields = ("number", "user__email")
    raw_id_fields = ("user", "shared_plan")
