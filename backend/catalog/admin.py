from django.contrib import admin

from catalog.models import Category, ServiceName


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_preset", "user")
    list_filter = ("is_preset",)
    search_fields = ("name", "user__email")


@admin.register(ServiceName)
class ServiceNameAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "is_preset", "user")
    list_filter = ("is_preset", "category")
    search_fields = ("name", "user__email")
