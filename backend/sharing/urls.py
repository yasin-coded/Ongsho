from django.urls import path

from sharing import views

urlpatterns = [
    path("shared-plans/<int:pk>/", views.shared_plan_detail, name="shared-plan-detail"),
    path("shared-plans/<int:pk>/invites/", views.shared_plan_invites, name="shared-plan-invites"),
    path("shared-plans/<int:pk>/members/", views.shared_plan_members, name="shared-plan-members"),
    path("shared-plans/<int:pk>/leave-request/", views.leave_request, name="shared-plan-leave-request"),
    path("shared-plans/<int:pk>/split/", views.shared_plan_split, name="shared-plan-split"),
    path("invites/<int:pk>/cancel/", views.invite_cancel, name="invite-cancel"),
    path("invites/<int:pk>/new-link/", views.invite_new_link, name="invite-new-link"),
    path("invites/<str:token>/", views.invite_public, name="invite-public"),
    path("invites/<str:token>/accept/", views.invite_accept_token, name="invite-accept-token"),
    path("invites/<str:token>/decline/", views.invite_decline_token, name="invite-decline-token"),
    path("invites/<str:token>/signup/", views.invite_signup, name="invite-signup"),
    path("members/<int:pk>/", views.member_detail, name="member-detail"),
    path("members/<int:pk>/balance/", views.member_balance, name="member-balance"),
    path("members/<int:pk>/leave/", views.owner_leave_decision, name="member-leave-decision"),
    path("members/<int:pk>/replace/", views.member_replace, name="member-replace"),
    path("me/invites/", views.my_pending_invites, name="me-invites"),
    path("me/invites/<int:pk>/accept/", views.my_invite_accept, name="me-invite-accept"),
    path("me/invites/<int:pk>/decline/", views.my_invite_decline, name="me-invite-decline"),
]
