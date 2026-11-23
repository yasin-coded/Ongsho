from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from core.views import health, health_ready

urlpatterns = [
    path("api/health/", health, name="health"),
    path("api/health/ready/", health_ready, name="health-ready"),
    path("api/auth/", include("accounts.urls")),
    path("api/me/", include("accounts.me_urls")),
    path("api/reminders/", include("accounts.reminder_urls")),
    path("api/", include("catalog.urls")),
    path("api/", include("plans.urls")),
    path("api/", include("billing.urls")),
    path("api/", include("notifications.urls")),
    path("api/", include("sharing.urls")),
    path("api/", include("dues.urls")),
    path("api/", include("payments.urls")),
    path("api/", include("reports.urls")),
]

if settings.ADMIN_ENABLED:
    urlpatterns = [path(settings.ADMIN_URL, admin.site.urls), *urlpatterns]