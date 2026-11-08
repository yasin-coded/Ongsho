from django.urls import path

from plans import subscription_views, views

urlpatterns = [
    path("exchange-rates/", views.exchange_rate_list_create, name="exchange-rate-list"),
    path("subscriptions/", subscription_views.subscription_list_create, name="subscription-list"),
    path("subscriptions/<int:pk>/", subscription_views.subscription_detail, name="subscription-detail"),
    path(
        "subscriptions/<int:pk>/price-changes/",
        subscription_views.price_change_list_create,
        name="subscription-price-changes",
    ),
]
