from django.contrib import admin

from sharing.models import Invite, Member, OwnershipTransfer, SharedPlan


@admin.register(SharedPlan)
class SharedPlanAdmin(admin.ModelAdmin):
    list_display = ("id", "subscription", "split_type")
    search_fields = ("subscription__plan_name",)
    raw_id_fields = ("subscription",)


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("shared_plan", "user", "status", "joined_on", "left_on")
    list_filter = ("status", "share_type")
    search_fields = ("user__email",)
    raw_id_fields = ("shared_plan", "user")


@admin.register(Invite)
class InviteAdmin(admin.ModelAdmin):
    list_display = ("email", "shared_plan", "status", "expires_on")
    list_filter = ("status",)
    search_fields = ("email",)
    raw_id_fields = ("shared_plan", "invited_by", "accepted_by")


@admin.register(OwnershipTransfer)
class OwnershipTransferAdmin(admin.ModelAdmin):
    list_display = ("shared_plan", "from_user", "to_user", "status", "created_at")
    list_filter = ("status",)
    raw_id_fields = ("shared_plan", "from_user", "to_user")
