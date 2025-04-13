from django.urls import path
from .views import (register_view, 
                    user_profile_view, 
                    add_user_view, 
                    edit_user_view, 
                    delete_user_view)
from .views import (CustomLoginView, 
                    CustomPasswordChangeView, 
                    CustomLoginViewWeb)
from django.contrib.auth.views import LogoutView

urlpatterns = [
    path('register/', register_view, name='register'),
    path('login/', CustomLoginViewWeb.as_view(), name='login'),
    path('logout/', LogoutView.as_view(next_page='login'), name='logout'),
    path('change-password/', CustomPasswordChangeView.as_view(), name='change_password'),
    path('profile/<int:user_id>/', user_profile_view, name='user_profile'),
    
    path('dashboard/users/add/', add_user_view, name='add_user'),
    path('dashboard/users/<int:user_id>/edit/', edit_user_view, name='edit_user'),
    path('dashboard/users/<int:user_id>/delete/', delete_user_view, name='delete_user'),
]
