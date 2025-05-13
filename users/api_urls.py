from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    UserRegistrationAPIView,
    UserLoginAPIView,
    UserLogoutAPIView,
    UserProfileAPIView,
    ChangePasswordAPIView,
    UserDeviceViewSet
)

router = DefaultRouter()
router.register(r'devices', UserDeviceViewSet, basename='userdevice')

urlpatterns = [
    path('register/', UserRegistrationAPIView.as_view(), name='api_user_register'),
    path('login/', UserLoginAPIView.as_view(), name='api_user_login'),
    path('logout/', UserLogoutAPIView.as_view(), name='api_user_logout'),
    path('profile/', UserProfileAPIView.as_view(), name='api_user_profile'),
    path('change-password/', ChangePasswordAPIView.as_view(), name='api_change_password'),
    path('', include(router.urls)),
]