from django.urls import path

from accounts import reminder_views

urlpatterns = [
    path("settings/", reminder_views.reminder_settings, name="reminder-settings"),
]
