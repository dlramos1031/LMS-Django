from django.urls import path
from .views import (
    RegisterView,
    CustomLoginView,
    LogoutView,
    CustomPasswordChangeView,
    UserProfileView,
    check_username,
    check_email,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='api_register'),
    path('login/', CustomLoginView.as_view(), name='api_login'),
    path('logout/', LogoutView.as_view(), name='api_logout'),
    path('change-password/', CustomPasswordChangeView.as_view(), name='api_change_password'),
    path('check-username/', check_username, name='check_username'),
    path('check-email/', check_email, name='check_email'),
    path('profile/', UserProfileView.as_view(), name='api_user_profile'),
]
