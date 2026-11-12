from django.urls import path

from notifications import views

urlpatterns = [
    path("notifications/", views.notification_list, name="notification-list"),
    path("notifications/read-all/", views.notification_read_all, name="notification-read-all"),
    path("notifications/<int:pk>/read/", views.notification_mark_read, name="notification-mark-read"),
]
