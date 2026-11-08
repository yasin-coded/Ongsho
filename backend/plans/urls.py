from django.urls import path

from plans import views

urlpatterns = [
    path("exchange-rates/", views.exchange_rate_list_create, name="exchange-rate-list"),
]
