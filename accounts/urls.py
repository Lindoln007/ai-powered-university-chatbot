from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("users", views.UserAdminViewSet, basename="user")

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="auth-register"),
    path("login/", views.LoginView.as_view(), name="auth-login"),
    path("logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("profile/", views.ProfileView.as_view(), name="auth-profile"),
    path("password/change/", views.PasswordChangeView.as_view(), name="auth-password-change"),
    path("", include(router.urls)),
]
