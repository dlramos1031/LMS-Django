from django.contrib.auth.decorators import user_passes_test
from django.urls import reverse_lazy

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