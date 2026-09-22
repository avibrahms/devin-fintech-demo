from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView

from core.views import demo_reset

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="refunds:list", permanent=False), name="home"),
    path("login/", auth_views.LoginView.as_view(redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("refunds/", include("refunds.urls")),
    path("kyc/", include("kyc.urls")),
    path("demo/reset/", demo_reset, name="demo_reset"),
    path("admin/", admin.site.urls),
]
