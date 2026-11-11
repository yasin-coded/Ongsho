from django.urls import path

from catalog import views

urlpatterns = [
    path("categories/", views.category_list_create, name="category-list"),
    path("categories/<int:pk>/", views.category_detail, name="category-detail"),
    path("service-names/", views.service_name_list_create, name="service-name-list"),
    path("service-names/<int:pk>/", views.service_name_detail, name="service-name-detail"),
]
