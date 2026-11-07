from django.urls import path

from accounts import views

urlpatterns = [
    path("register/", views.register_view, name="auth-register"),
    path("verify-email/", views.verify_email_view, name="auth-verify-email"),
    path("resend-verification/", views.resend_verification_view, name="auth-resend-verification"),
    path("login/", views.login_view, name="auth-login"),
    path("refresh/", views.refresh_view, name="auth-refresh"),
    path("logout/", views.logout_view, name="auth-logout"),
    path("password-reset/", views.password_reset_view, name="auth-password-reset"),
    path("password-reset/confirm/", views.password_reset_confirm_view, name="auth-password-reset-confirm"),
]
