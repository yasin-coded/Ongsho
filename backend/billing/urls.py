from django.urls import path

from billing import views

urlpatterns = [
    path("charges/", views.charge_list, name="charge-list"),
    path("charges/generate/", views.charge_generate, name="charge-generate"),
    path("charges/<int:pk>/rate/", views.charge_rate, name="charge-rate"),
    path("calendar/", views.calendar_view, name="calendar"),
]
