from django.urls import path

from accounts import me_views

urlpatterns = [
    path("", me_views.me_profile, name="me-profile"),
    path("password/", me_views.me_password, name="me-password"),
    path("email/", me_views.me_email, name="me-email"),
    path("email/verify/", me_views.me_email_verify, name="me-email-verify"),
]
