from django.urls import path

from . import views

app_name = "kyc"

urlpatterns = [
    path("", views.case_list, name="list"),
]
