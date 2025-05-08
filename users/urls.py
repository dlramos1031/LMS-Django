from django.urls import path
from .views import (
    register_view, 
    user_profile_view, 
    add_user_view, 
    edit_user_view, 
    delete_user_view, 
    edit_profile_view,
    dashboard_users_view,
    CustomPasswordChangeView, 
    CustomLoginViewWeb
)
from django.contrib.auth.views import LogoutView as DjangoLogoutView

urlpatterns = [
    # Web auth
    path('register/', register_view, name='register'),
    path('login/', CustomLoginViewWeb.as_view(), name='login'),
    path('logout/', DjangoLogoutView.as_view(next_page='login'), name='logout'),
    path('change-password/', CustomPasswordChangeView.as_view(), name='change_password'),

    # Profile
    path('profile/<int:user_id>/', user_profile_view, name='user_profile'),
    path('profile/<int:user_id>/edit', edit_profile_view, name='edit_profile'),

    # Dashboard user management
    path('dashboard/users/', dashboard_users_view, name='dashboard_users'),
    path('dashboard/users/add/', add_user_view, name='add_user'),
    path('dashboard/users/<int:user_id>/edit/', edit_user_view, name='edit_user'),
    path('dashboard/users/<int:user_id>/delete/', delete_user_view, name='delete_user'),
]
