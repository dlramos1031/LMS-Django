from django.urls import path, reverse_lazy
from . import views
from django.contrib.auth import views as auth_views

app_name = 'users'

urlpatterns = [
    # --- Borrower Web Portal & General Auth URLs ---
    path('register/', views.user_register_view, name='register'),
    path('login/', views.user_login_view, name='login'),
    path('logout/', views.user_logout_view, name='logout'),
    path('password_change/', views.change_password_view, name='password_change'),
    
    # --- Borrower Profile and Borrowing URLs ---
    path('profile/', views.user_profile_view, name='my_profile'),
    path('profile/edit/', views.user_profile_edit_view, name='edit_my_profile'),
    path('my-borrowings/', views.my_borrowings_view, name='my_borrowings'),
    path('my-reservations/', views.my_reservations_view, name='my_reservations'),

    # --- Password Reset URLs (for users who forgot their password) ---
    path('password_reset/', 
         auth_views.PasswordResetView.as_view(
             template_name='users/registration/password_reset_form.html',
             email_template_name='users/registration/password_reset_email.html',
             subject_template_name='users/registration/password_reset_subject.txt',
             success_url=reverse_lazy('users:password_reset_done') # Redirect after form submission
         ), 
         name='password_reset'),

    path('password_reset/done/', 
         auth_views.PasswordResetDoneView.as_view(
             template_name='users/registration/password_reset_done.html'
         ), 
         name='password_reset_done'),

    path('reset/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(
             template_name='users/registration/password_reset_confirm.html',
             success_url=reverse_lazy('users:password_reset_complete')
         ), 
         name='password_reset_confirm'),

    path('reset/done/', 
         auth_views.PasswordResetCompleteView.as_view(
             template_name='users/registration/password_reset_complete.html'
         ), 
         name='password_reset_complete'),

    # --- Staff Dashboard: Login Page URL ---
    path('dashboard/login/', views.staff_login_view, name='staff_login'),

    # --- Staff Dashboard: Borrower Management URLs ---
    path('dashboard/borrowers/', views.StaffBorrowerListView.as_view(), name='dashboard_borrower_list'),
    path('dashboard/borrowers/add/', views.StaffBorrowerCreateView.as_view(), name='dashboard_borrower_add'),
    path('dashboard/borrowers/view/<int:pk>/', views.StaffUserDetailView.as_view(), name='dashboard_borrower_detail'),
    path('dashboard/borrowers/edit/<int:pk>/', views.StaffBorrowerUpdateView.as_view(), name='dashboard_borrower_edit'),
    path('dashboard/borrowers/delete/<int:pk>/confirm/', views.StaffBorrowerDeleteView.as_view(), name='dashboard_borrower_delete_confirm'),

    # --- Staff Dashboard: Staff Management URLs (Admin Only) ---
    path('dashboard/staff/', views.AdminStaffListView.as_view(), name='dashboard_staff_list'),
    path('dashboard/staff/add/', views.AdminStaffCreateView.as_view(), name='dashboard_staff_add'),
    path('dashboard/staff/edit/<int:pk>/', views.AdminStaffUpdateView.as_view(), name='dashboard_staff_edit'),
    path('dashboard/staff/delete/<int:pk>/confirm/', views.AdminStaffDeleteView.as_view(), name='dashboard_staff_delete_confirm'),
]