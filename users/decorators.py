from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from functools import wraps

def redirect_authenticated_user(view_func):
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated:
            if request.user.role in ['librarian', 'admin'] or request.user.is_staff:
                return redirect('librarian_dashboard')
            else:
                return redirect('books_list')
        return view_func(request, *args, **kwargs)
    return wrapper

def admin_only(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role in ['librarian', 'admin'] or request.user.is_staff:
            return view_func(request, *args, **kwargs)
        else:
            return redirect('books_list')
    return wrapper

def members_only(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role in ['librarian', 'admin'] or request.user.is_staff:
            return redirect('librarian_dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper