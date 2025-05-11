from django.urls import path
from . import views
# from django.contrib.auth import views as auth_views # If using built-in views for password reset

app_name = 'users'

urlpatterns = [
    # Borrower Web Portal & General Auth
    path('register/', views.user_register_view, name='register'),
    path('login/', views.user_login_view, name='login'),
    path('logout/', views.user_logout_view, name='logout'),
    path('password_change/', views.change_password_view, name='password_change'),
    # path('password_reset/', auth_views.PasswordResetView.as_view(template_name='users/registration/password_reset_form.html'), name='password_reset'),
    # ... other password reset views from django.contrib.auth.urls ...

    path('profile/', views.user_profile_view, name='my_profile'),
    path('profile/edit/', views.user_profile_edit_view, name='edit_my_profile'),
    path('my-borrowings/', views.my_borrowings_view, name='my_borrowings'),
    path('my-reservations/', views.my_reservations_view, name='my_reservations'),

    # Staff Dashboard User Management
    path('dashboard/users/', views.StaffUserListView.as_view(), name='dashboard_user_list'),
    path('dashboard/users/add/', views.StaffUserCreateView.as_view(), name='dashboard_user_add'),
    path('dashboard/users/edit/<int:pk>/', views.StaffUserUpdateView.as_view(), name='dashboard_user_edit'),
    path('dashboard/users/delete/<int:pk>/', views.StaffUserDeleteView.as_view(), name='dashboard_user_delete'),
]