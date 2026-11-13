from django.urls import path

from reports import views

urlpatterns = [
    path("dashboard/summary/", views.dashboard_summary, name="dashboard-summary"),
    path("dashboard/forecast/", views.dashboard_forecast, name="dashboard-forecast"),
]
