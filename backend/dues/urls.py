from django.urls import path

from dues import views

urlpatterns = [
    path("dues/", views.due_list, name="due-list"),
]
