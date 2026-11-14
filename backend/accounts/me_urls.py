from django.urls import path

from accounts import me_shared_views, me_views
from reports import views as report_views

urlpatterns = [
    path("", me_views.me_profile, name="me-profile"),
    path("password/", me_views.me_password, name="me-password"),
    path("email/", me_views.me_email, name="me-email"),
    path("email/verify/", me_views.me_email_verify, name="me-email-verify"),
    path("email/resend/", me_views.me_email_resend, name="me-email-resend"),
    path("nav-counts/", me_views.me_nav_counts, name="me-nav-counts"),
    path("shared-plans/", me_shared_views.me_shared_plan_list, name="me-shared-plan-list"),
    path("shared-plans/<int:pk>/", me_shared_views.me_shared_plan_detail, name="me-shared-plan-detail"),
    path("shared-plans/<int:pk>/statement/", report_views.member_statement, name="me-shared-plan-statement"),
]
