from django.urls import path

from plans import subscription_status_views, subscription_views, views
from sharing import views as sharing_views

urlpatterns = [
    path("exchange-rates/", views.exchange_rate_list_create, name="exchange-rate-list"),
    path("subscriptions/", subscription_views.subscription_list_create, name="subscription-list"),
    path("subscriptions/<int:pk>/", subscription_views.subscription_detail, name="subscription-detail"),
    path(
        "subscriptions/<int:pk>/price-changes/",
        subscription_views.price_change_list_create,
        name="subscription-price-changes",
    ),
    path(
        "subscriptions/<int:pk>/pause/",
        subscription_status_views.subscription_pause,
        name="subscription-pause",
    ),
    path(
        "subscriptions/<int:pk>/resume/",
        subscription_status_views.subscription_resume,
        name="subscription-resume",
    ),
    path(
        "subscriptions/<int:pk>/cancel/",
        subscription_status_views.subscription_cancel,
        name="subscription-cancel",
    ),
    path(
        "subscriptions/<int:pk>/renew/",
        subscription_status_views.subscription_renew,
        name="subscription-renew",
    ),
    path(
        "subscriptions/<int:pk>/share/",
        sharing_views.subscription_share,
        name="subscription-share",
    ),
]
