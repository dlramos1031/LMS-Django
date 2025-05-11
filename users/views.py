from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import views as auth_views # For built-in auth views if you use them for password reset
from django.contrib.auth import login, get_user_model, authenticate, logout, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView # Added CBVs
from django.db.models import Q

# DRF Imports
from rest_framework import generics, permissions, status, viewsets, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken

from .serializers import RegisterSerializer, UserSerializer, UserDeviceSerializer, ChangePasswordSerializer
from .forms import (
    UserRegistrationForm,
    CustomPasswordChangeForm,
    BorrowerProfileUpdateForm
)
from .models import CustomUser, UserDevice
from books.models import Borrowing, Notification

User = get_user_model()

# --- Helper for Staff Permissions ---
def is_staff_user(user):
    return user.is_authenticated and (user.role in ['LIBRARIAN', 'ADMIN'] or user.is_staff)

class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = reverse_lazy('users:login')

    def test_func(self):
        return is_staff_user(self.request.user)

    def handle_no_permission(self):
        messages.error(self.request, _("You do not have permission to access this page."))
        if self.request.user.is_authenticated and not is_staff_user(self.request.user):
            return redirect('books:portal_catalog')
        return super().handle_no_permission()


# === Django Template-Rendering Views ===

def user_register_view(request):
    if request.user.is_authenticated:
        return redirect('books:portal_catalog')

    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, _('Registration successful! Please log in.'))
            return redirect('users:login')
        else:
            pass
    else:
        form = UserRegistrationForm()
    return render(request, 'users/registration/register.html', {'form': form, 'page_title': _('Register')})


def user_login_view(request):
    print("Is user logged in?", request.user.is_authenticated)
    if request.user.is_authenticated:
        if is_staff_user(request.user):
            return redirect('books:dashboard_home')
        return redirect('books:portal_catalog')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, _('Login successful.'))
                if is_staff_user(user):
                    return redirect('books:dashboard_home')
                else:
                    return redirect('books:portal_catalog')
            else:
                messages.error(request, _('Invalid username or password.'))
    else:
        form = AuthenticationForm()
    return render(request, 'users/registration/login.html', {'form': form, 'page_title': _('Login')})

@login_required
def user_logout_view(request):
    logout(request)
    messages.info(request, _('You have been successfully logged out.'))
    return redirect('users:login')


@login_required
def user_profile_view(request):
    user = get_object_or_404(CustomUser, pk=request.user.pk)
    user_borrowings = Borrowing.objects.filter(borrower=user).select_related('book_copy__book').order_by('-issue_date')[:10]
    context = {
        'profile_user': user,
        'borrowings': user_borrowings,
        'page_title': _(f"{user.username}'s Profile")
    }
    return render(request, 'users/portal/profile.html', context)

@login_required
def user_profile_edit_view(request):
    if request.method == 'POST':
        form = BorrowerProfileUpdateForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, _('Your profile has been updated successfully.'))
            return redirect('users:my_profile')
        else:
            messages.error(request, _('Please correct the errors below.'))
    else:
        form = BorrowerProfileUpdateForm(instance=request.user)

    context = {
        'form': form,
        'page_title': _('Edit Profile')
    }
    return render(request, 'users/portal/profile_edit_form.html', context)


@login_required
def change_password_view(request):
    if request.method == 'POST':
        form = CustomPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, _('Your password was successfully updated!'))
            return redirect('users:my_profile')
        else:
            messages.error(request, _('Please correct the errors below.'))
    else:
        form = CustomPasswordChangeForm(request.user)
    return render(request, 'users/registration/password_change_form.html', {
        'form': form,
        'page_title': _('Change Password')
    })


# --- New Borrower Web Portal Views ---
@login_required
def my_borrowings_view(request):
    user_borrowings = Borrowing.objects.filter(borrower=request.user).select_related('book_copy__book').order_by('-issue_date')
    active_borrowings = user_borrowings.filter(status__in=['ACTIVE', 'OVERDUE', 'REQUESTED'])
    past_borrowings = user_borrowings.filter(status__in=['RETURNED', 'RETURNED_LATE', 'CANCELLED', 'LOST_BY_BORROWER'])
    context = {
        'active_borrowings': active_borrowings,
        'past_borrowings': past_borrowings,
        'page_title': _('My Borrowings')
    }
    return render(request, 'users/portal/my_borrowings.html', context)

@login_required
def my_reservations_view(request):
    user_reservations = []
    context = {
        'reservations': user_reservations,
        'page_title': _('My Reservations')
    }
    return render(request, 'users/portal/my_reservations.html', context)


# --- Staff Dashboard User Management Views ---

class StaffUserListView(StaffRequiredMixin, ListView):
    model = CustomUser
    template_name = 'users/dashboard/user_list.html'
    context_object_name = 'users_list'
    paginate_by = 15

    def get_queryset(self):
        queryset = CustomUser.objects.all().order_by('last_name', 'first_name')
        search_term = self.request.GET.get('search')
        role_filter = self.request.GET.get('role')
        if search_term:
            queryset = queryset.filter(
                Q(username__icontains=search_term) |
                Q(first_name__icontains=search_term) |
                Q(last_name__icontains=search_term) |
                Q(email__icontains=search_term)
            )
        if role_filter:
            queryset = queryset.filter(role=role_filter)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Manage Users')
        context['current_search'] = self.request.GET.get('search', '')
        context['current_role_filter'] = self.request.GET.get('role', '')
        context['role_choices'] = CustomUser.ROLE_CHOICES
        return context

class StaffUserCreateView(StaffRequiredMixin, CreateView):
    model = CustomUser
    fields = ['username', 'password', 'first_name', 'last_name', 'email', 'role', 'borrower_id_value', 'borrower_id_label', 'borrower_type', 'is_active', 'is_staff', 'is_superuser'] # Example fields
    template_name = 'users/dashboard/user_form.html'
    success_url = reverse_lazy('users:dashboard_user_list')

    def form_valid(self, form):
        user = form.save(commit=False)
        user.set_password(form.cleaned_data["password"])
        user.save()
        messages.success(self.request, _(f"User '{user.username}' created successfully."))
        return redirect(self.success_url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Add New User')
        context['form_mode'] = 'create'
        return context

class StaffUserUpdateView(StaffRequiredMixin, UpdateView):
    model = CustomUser
    fields = ['username', 'first_name', 'last_name', 'email', 'role', 'borrower_id_value', 'borrower_id_label', 'borrower_type', 'is_active', 'is_staff', 'is_superuser'] # Password change should be separate
    template_name = 'users/dashboard/user_form.html'
    success_url = reverse_lazy('users:dashboard_user_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _(f"Edit User: {self.object.username}")
        context['form_mode'] = 'edit'
        return context

    def form_valid(self, form):
        messages.success(self.request, _(f"User '{form.instance.username}' updated successfully."))
        return super().form_valid(form)

class StaffUserDeleteView(StaffRequiredMixin, DeleteView):
    model = CustomUser
    template_name = 'users/dashboard/user_confirm_delete.html'
    success_url = reverse_lazy('users:dashboard_user_list')
    context_object_name = 'user_to_delete'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _(f"Confirm Delete User: {self.object.username}")
        return context

    def form_valid(self, form):
        if self.object.role == 'BORROWER' and Borrowing.objects.filter(borrower=self.object, status__in=['ACTIVE', 'OVERDUE']).exists():
            messages.error(self.request, _(f"Cannot delete borrower '{self.object.username}' with active or overdue loans."))
            return redirect('users:dashboard_user_list')
        messages.success(self.request, _(f"User '{self.object.username}' deleted successfully."))
        return super().form_valid(form)


# === DRF API Views ===

class UserRegistrationAPIView(generics.CreateAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

class UserLoginAPIView(ObtainAuthToken):
    """ API view for user login, returns auth token """
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        token, created = Token.objects.get_or_create(user=user)
        user_data = UserSerializer(user, context=self.get_serializer_context()).data
        return Response({
            'token': token.key,
            'user': user_data
        })

class UserLogoutAPIView(APIView):
    """ API view for user logout, deletes auth token """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        try:
            request.user.auth_token.delete()
        except (AttributeError, Token.DoesNotExist):
            pass
        return Response({"detail": _("Successfully logged out.")}, status=status.HTTP_200_OK)


class UserProfileAPIView(generics.RetrieveUpdateAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class ChangePasswordAPIView(generics.UpdateAPIView):
    serializer_class = ChangePasswordSerializer
    model = CustomUser
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, queryset=None):
        return self.request.user

    def update(self, request, *args, **kwargs):
        self.object = self.get_object()
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            if not self.object.check_password(serializer.data.get("old_password")):
                return Response({"old_password": [_("Wrong password.")]}, status=status.HTTP_400_BAD_REQUEST)
            self.object.set_password(serializer.data.get("new_password"))
            self.object.save()
            return Response({"detail": _("Password changed successfully.")}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserDeviceViewSet(viewsets.ModelViewSet):
    queryset = UserDevice.objects.all()
    serializer_class = UserDeviceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return UserDevice.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        registration_id = serializer.validated_data.get('registration_id')
        UserDevice.objects.update_or_create(
            user=self.request.user,
            registration_id=registration_id,
            defaults={'is_active': True}
        )
        instance, created = UserDevice.objects.update_or_create(
            registration_id=registration_id,
            defaults={'user': self.request.user, 'is_active': True}
        )
