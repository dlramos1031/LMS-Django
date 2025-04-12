from django.urls import path
from .views import register_view, CustomLoginView, CustomPasswordChangeView, CustomLoginViewWeb
from django.contrib.auth.views import LogoutView

urlpatterns = [
    path('register/', register_view, name='register'),
    path('login/', CustomLoginViewWeb.as_view(), name='login'),
    path('logout/', LogoutView.as_view(next_page='login'), name='logout'),
    path('change-password/', CustomPasswordChangeView.as_view(), name='change_password'),
]
