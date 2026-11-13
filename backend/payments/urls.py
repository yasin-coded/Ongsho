from django.urls import path

from payments import views

urlpatterns = [
    path("payments/", views.payment_submit, name="payment-submit"),
    path("payments/<int:pk>/waive/", views.payment_waive, name="payment-waive"),
    path("payments/<int:pk>/confirm/", views.payment_confirm, name="payment-confirm"),
    path("payments/<int:pk>/reject/", views.payment_reject, name="payment-reject"),
    path("payments/<int:pk>/reverse/", views.payment_reverse, name="payment-reverse"),
    path("dues/<int:pk>/mark-paid/", views.due_mark_paid, name="due-mark-paid"),
    path("dues/<int:pk>/waive/", views.due_waive, name="due-waive"),
    path("dues/<int:pk>/set-due/", views.due_set_due, name="due-set-due"),
]
