from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _

def admin_only(function=None, redirect_field_name=None, login_url=None):
    """
    Decorator for views that checks that the user is logged in and is an ADMIN.
    """
    if login_url is None:
        login_url = reverse_lazy('users:login')

    actual_decorator = user_passes_test(
        lambda u: u.is_authenticated and (u.role == 'ADMIN' or u.is_staff),
        login_url=login_url,
        redirect_field_name=redirect_field_name
    )
    if function:
        return actual_decorator(function)
    return actual_decorator

def members_only(function=None, redirect_field_name=None, login_url=None):
    """
    Decorator for views that checks that the user is logged in (any role).
    If you want it to be specifically for BORROWERs, adjust the lambda.
    """
    if login_url is None:
        login_url = reverse_lazy('users:login')

    actual_decorator = user_passes_test(
        lambda u: u.is_authenticated,
        login_url=login_url,
        redirect_field_name=redirect_field_name
    )
    if function:
        return actual_decorator(function)
    return actual_decorator

def is_staff_user(user):
    """Checks if the user is authenticated and has a staff-like role."""
    return user.is_authenticated and (user.role in ['LIBRARIAN', 'ADMIN'] or user.is_staff)

class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Mixin to require staff privileges for accessing a view."""
    login_url = reverse_lazy('users:login')

    def test_func(self):
        return is_staff_user(self.request.user)

    def handle_no_permission(self):
        messages.error(self.request, _("You do not have permission to access this page."))
        if self.request.user.is_authenticated and not is_staff_user(self.request.user):
            return redirect('books:portal_catalog')
        return super().handle_no_permission()

class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = reverse_lazy('users:login') # Or your staff login if different

    def test_func(self):
        return self.request.user.is_authenticated and \
               (self.request.user.is_superuser or self.request.user.role == 'ADMIN')

    def handle_no_permission(self):
        messages.error(self.request, _("You must be an Administrator to access this page."))
        if self.request.user.is_authenticated:
            return redirect('books:dashboard_home') # Redirect to dashboard home
        return super().handle_no_permission() # Redirects to login_url