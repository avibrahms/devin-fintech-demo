from django.urls import path

from . import views

app_name = "refunds"

urlpatterns = [
    path("", views.refund_list, name="list"),
    path("<int:pk>/", views.refund_detail, name="detail"),
    path("<int:pk>/decide/", views.decide_refund, name="decide"),
    path("payments/", views.payment_list, name="payments"),
    path("payments/<int:payment_id>/request/", views.request_refund, name="request"),
]
