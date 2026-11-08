from django.urls import path

from catalog import views

urlpatterns = [
    path("categories/", views.category_list_create, name="category-list"),
    path("service-names/", views.service_name_list_create, name="service-name-list"),
]
