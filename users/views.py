from django.contrib import messages
from django.core.paginator import Paginator
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
from django.http import JsonResponse
from django.views import View

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
    BorrowerProfileUpdateForm,
    StaffBorrowerCreateForm,
    StaffBorrowerChangeForm,
    AdminStaffCreateForm,
    AdminStaffChangeForm
)
from .models import CustomUser, UserDevice
from .decorators import StaffRequiredMixin, AdminRequiredMixin
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
                if is_staff_user(user):
                    messages.error(request, _("Staff accounts must log in via the Staff Login Page."))
                    logout(request) 
                    return redirect('users:staff_login')
                else:
                    login(request, user)
                    messages.success(request, _('Login successful.'))
                    return redirect('books:portal_catalog')
            else:
                messages.error(request, _('Invalid username or password.'))
    else:
        form = AuthenticationForm()
    return render(request, 'users/registration/login.html', {'form': form, 'page_title': _('Login')})

@login_required
def user_logout_view(request):
    user_role = request.user.role
    logout(request)
    messages.info(request, _('You have been successfully logged out.'))
    if user_role == 'BORROWER':
        return redirect('users:login')
    else:
        return redirect('users:staff_login')


@login_required
def user_profile_view(request):
    profile_user = get_object_or_404(CustomUser, pk=request.user.pk)
    user_borrowings = Borrowing.objects.filter(borrower=profile_user).select_related('book_copy__book').order_by('-issue_date')[:5]
    context = {
        'profile_user': profile_user,
        'borrowings': user_borrowings,
        'page_title': _(f"My Profile: {profile_user.username}"),
        'view_context': 'portal',
        'is_own_profile': True,
        'back_url': reverse_lazy('books:portal_catalog') # Or None if no explicit back button needed
    }
    return render(request, 'users/portal/profile.html', context) # Point to the wrapper

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
    if request.user.role in ['LIBRARIAN', 'ADMIN'] or request.user.is_staff:
        messages.info(request, _("Staff members should use the dashboard to manage borrowings."))
        return redirect('books:dashboard_home')

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
    
    context = {
        'form': form,
        'page_title': _('Change Password'),
        'view_context': 'portal',
    }
    return render(request, 'users/registration/password_change_form.html', context)


# --- New Borrower Web Portal Views ---
@login_required
def my_borrowings_view(request):
    if request.user.role in ['LIBRARIAN', 'ADMIN'] or request.user.is_staff:
        messages.info(request, _("Staff members should use the dashboard to manage borrowings."))
        return redirect('books:dashboard_home')
    
    user_borrowings = Borrowing.objects.filter(borrower=request.user).select_related('book_copy__book').order_by('-issue_date', '-request_date')

    active_borrowing_statuses = ['ACTIVE', 'OVERDUE', 'REQUESTED']
    past_borrowing_statuses = ['RETURNED', 'RETURNED_LATE', 'CANCELLED', 'REJECTED', 'LOST_BY_BORROWER']

    active_borrowings = user_borrowings.filter(status__in=active_borrowing_statuses)
    past_borrowings = user_borrowings.filter(status__in=past_borrowing_statuses)

    context = {
        'active_borrowings': active_borrowings,
        'past_borrowings': past_borrowings,
        'page_title': _('My Borrowings'),
        'view_context': 'portal',
    }
    return render(request, 'users/portal/my_borrowings.html', context)

@login_required
def my_reservations_view(request):
    user_reservations = []
    context = {
        'reservations': user_reservations,
        'page_title': _('My Reservations')
    }
    return render(request, 'users/portal/my_borrowings.html', context)

def staff_login_view(request):
    if request.user.is_authenticated and is_staff_user(request.user):
        return redirect('books:dashboard_home')
    elif request.user.is_authenticated: 
        logout(request) 
        messages.info(request, _("You have been logged out. This login is for staff accounts only."))
        return redirect('users:staff_login')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            if user is not None:
                if is_staff_user(user):
                    login(request, user)
                    messages.success(request, _('Staff login successful.'))
                    return redirect(request.GET.get('next', 'books:dashboard_home'))
                else:
                    messages.error(request, _("This login page is for staff accounts only. Borrower accounts should use the Portal Login."))
                    return redirect('users:login')
            else:
                messages.error(request, _('Invalid staff credentials.'))
    else:
        form = AuthenticationForm()
    
    context = {
        'form': form,
        'page_title': _('Staff Login'),
    }
    return render(request, 'users/registration/staff_login.html', context)


    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            if user is not None and is_staff_user(user): # Crucial check
                login(request, user)
                messages.success(request, _('Staff login successful.'))
                return redirect(request.GET.get('next', 'books:dashboard_home'))
            else:
                messages.error(request, _('Invalid staff credentials or not a staff account.'))
        # else: form errors will be shown
    else:
        form = AuthenticationForm()
    
    context = {
        'form': form,
        'page_title': _('Staff Login'),
        'site_header': "LMS Staff Portal"
    }
    return render(request, 'users/registration/staff_login.html', context)


class StaffUserDetailView(StaffRequiredMixin, DetailView):
    model = CustomUser
    template_name = 'users/dashboard/user_detail.html'
    context_object_name = 'profile_user'
    pk_url_kwarg = 'pk'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        target_user = self.get_object()
        context['page_title'] = _(f"User Profile: {target_user.username}")
        context['view_context'] = 'dashboard'
        context['is_own_profile'] = (self.request.user.pk == target_user.pk)

        can_edit = False
        if self.request.user.is_superuser:
            can_edit = True
            if self.request.user.pk == target_user.pk:
                pass
        elif self.request.user.role == 'LIBRARIAN':
            if target_user.role == 'BORROWER' and not target_user.is_staff:
                can_edit = True
        context['can_edit_this_profile'] = can_edit

        all_borrowings = Borrowing.objects.filter(borrower=target_user).select_related('book_copy__book').order_by('-issue_date')
        paginator = Paginator(all_borrowings, 10)
        page_number = self.request.GET.get('page')
        context['borrowings'] = paginator.get_page(page_number)
        query_params = self.request.GET.copy()
        query_params.pop('page', None)
        context['other_query_params_borrowings'] = query_params.urlencode()


        if target_user.role == 'BORROWER' and not target_user.is_staff:
            context['back_url'] = reverse_lazy('users:dashboard_borrower_list')
        elif target_user.is_staff or target_user.is_superuser:
            context['back_url'] = reverse_lazy('users:dashboard_staff_list')
        return context


# --- Staff Dashboard Borrower Management Views ---

class StaffBorrowerListView(StaffRequiredMixin, ListView):
    model = CustomUser
    template_name = 'users/dashboard/borrower_list.html'
    context_object_name = 'borrowers'
    paginate_by = 5


    def get_queryset(self):
        queryset = CustomUser.objects.filter(role='BORROWER').order_by('last_name', 'first_name')
        search_term = self.request.GET.get('search', '').strip()
        borrower_type_filter = self.request.GET.get('borrower_type', '').strip()
        status_filter = self.request.GET.get('status', '').strip()

        if search_term:
            queryset = queryset.filter(
                Q(username__icontains=search_term) |
                Q(first_name__icontains=search_term) |
                Q(last_name__icontains=search_term) |
                Q(email__icontains=search_term) |
                Q(borrower_id_value__icontains=search_term)
            )
        if borrower_type_filter:
            queryset = queryset.filter(borrower_type=borrower_type_filter)
        
        if status_filter:
            if status_filter == 'active':
                queryset = queryset.filter(is_active=True)
            elif status_filter == 'inactive':
                queryset = queryset.filter(is_active=False)
                
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Manage Borrowers')

        context['current_search'] = self.request.GET.get('search', '')
        context['borrower_type_choices'] = CustomUser.BORROWER_TYPE_CHOICES
        context['current_borrower_type_filter'] = self.request.GET.get('borrower_type', '')
        
        # Add status filter choices and current value
        context['status_choices'] = [
            ('active', _('Active')),
            ('inactive', _('Inactive')),
        ]
        context['current_status_filter'] = self.request.GET.get('status', '')

        query_params = self.request.GET.copy()
        query_params.pop('page', None)
        context['other_query_params'] = query_params.urlencode()
        
        return context


class StaffBorrowerCreateView(StaffRequiredMixin, CreateView):
    model = CustomUser
    form_class = StaffBorrowerCreateForm
    template_name = 'users/dashboard/borrower_form.html'
    success_url = reverse_lazy('users:dashboard_borrower_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['requesting_user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Add New Borrower')
        context['form_mode'] = 'create'
        return context

    def form_valid(self, form):
        # Role is set to BORROWER in StaffBorrowerCreateForm.save()
        messages.success(self.request, _(f"Borrower '{form.instance.username}' created successfully."))
        return super().form_valid(form)


class StaffBorrowerUpdateView(StaffRequiredMixin, UpdateView):
    model = CustomUser
    form_class = StaffBorrowerChangeForm
    template_name = 'users/dashboard/borrower_form.html'
    success_url = reverse_lazy('users:dashboard_borrower_list')
    context_object_name = 'user_to_edit'

    def get_queryset(self):
        return CustomUser.objects.filter(role='BORROWER')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['requesting_user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _(f"Edit Borrower: {self.object.username}")
        context['form_mode'] = 'edit'
        return context

    def form_valid(self, form):
        messages.success(self.request, _(f"Borrower '{form.instance.username}' updated successfully."))
        return super().form_valid(form)


class StaffBorrowerDeleteView(StaffRequiredMixin, DeleteView):
    model = CustomUser
    template_name = 'users/dashboard/borrower_confirm_delete.html'
    success_url = reverse_lazy('users:dashboard_borrower_list')
    context_object_name = 'user_to_delete'

    def get_queryset(self):
        return CustomUser.objects.filter(role='BORROWER')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _(f"Confirm Delete Borrower: {self.object.username}")
        return context

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        # Add any checks here, e.g., if borrower has active loans
        # if self.object.borrowings.filter(status__in=['ACTIVE', 'OVERDUE']).exists():
        #     messages.error(request, _("Cannot delete borrower with active loans."))
        #     return redirect('users:dashboard_borrower_list')
        messages.success(request, _(f"Borrower '{self.object.username}' deleted successfully."))
        return super().delete(request, *args, **kwargs)


# --- Staff Dashboard Staff Management Views ---
class AdminStaffListView(AdminRequiredMixin, ListView):
    model = CustomUser
    template_name = 'users/dashboard/staff_list.html'
    context_object_name = 'staff_members'
    paginate_by = 15

    def get_queryset(self):
        queryset = CustomUser.objects.filter(role__in=['LIBRARIAN', 'ADMIN']).order_by('role', 'last_name', 'first_name')
        search_term = self.request.GET.get('search', '').strip()
        staff_role_filter = self.request.GET.get('staff_role', '').strip()
        if search_term:
            queryset = queryset.filter(
                Q(username__icontains=search_term) |
                Q(first_name__icontains=search_term) |
                Q(last_name__icontains=search_term) |
                Q(email__icontains=search_term)
            )
        if staff_role_filter:
            queryset = queryset.filter(role=staff_role_filter)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Manage Staff Accounts')
        context['current_search'] = self.request.GET.get('search', '')
        context['current_staff_role_filter'] = self.request.GET.get('staff_role', '')
        context['staff_role_choices'] = [('LIBRARIAN', _('Librarian')), ('ADMIN', _('Administrator'))]
        query_params = self.request.GET.copy()
        query_params.pop('page', None)
        context['other_query_params'] = query_params.urlencode()

        return context

class AdminStaffCreateView(AdminRequiredMixin, CreateView):
    model = CustomUser
    form_class = AdminStaffCreateForm # Use the new form
    template_name = 'users/dashboard/staff_form.html' # NEW TEMPLATE
    success_url = reverse_lazy('users:dashboard_staff_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['requesting_user'] = self.request.user # Pass for context if form needs it
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Add New Staff Member')
        context['form_mode'] = 'create'
        return context

    def form_valid(self, form):
        # Role, is_staff, is_superuser are handled in AdminStaffCreateForm.save()
        messages.success(self.request, _(f"Staff member '{form.instance.username}' created successfully."))
        return super().form_valid(form)

class AdminStaffUpdateView(AdminRequiredMixin, UpdateView):
    model = CustomUser
    form_class = AdminStaffChangeForm # Use the new form
    template_name = 'users/dashboard/staff_form.html' # NEW TEMPLATE
    success_url = reverse_lazy('users:dashboard_staff_list')
    context_object_name = 'user_to_edit'

    def get_queryset(self): # Admins can edit Librarians and other Admins
        return CustomUser.objects.filter(role__in=['LIBRARIAN', 'ADMIN'])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['requesting_user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _(f"Edit Staff: {self.object.username}")
        context['form_mode'] = 'edit'
        return context

    def form_valid(self, form):
        # Logic to ensure an admin doesn't de-admin themselves if they are the only one,
        # or set is_staff/is_superuser based on role, is handled in AdminStaffChangeForm.clean()
        messages.success(self.request, _(f"Staff member '{form.instance.username}' updated successfully."))
        return super().form_valid(form)

class AdminStaffDeleteView(AdminRequiredMixin, DeleteView):
    model = CustomUser
    template_name = 'users/dashboard/staff_confirm_delete.html' # NEW TEMPLATE
    success_url = reverse_lazy('users:dashboard_staff_list')
    context_object_name = 'user_to_delete'

    def get_queryset(self):
        # Admins can delete Librarians and other Admins (except themselves)
        return CustomUser.objects.filter(role__in=['LIBRARIAN', 'ADMIN']).exclude(pk=self.request.user.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _(f"Confirm Delete Staff: {self.object.username}")
        return context

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.pk == request.user.pk: # Should be caught by queryset, but double check
            messages.error(request, _("You cannot delete your own account."))
            return redirect('users:dashboard_staff_list')
        # Add other checks if needed (e.g., ensure at least one superuser remains)
        messages.success(request, _(f"Staff member '{self.object.username}' deleted successfully."))
        return super().delete(request, *args, **kwargs)


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
        print(f"Token: {token.key}")
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

# === API Views for Availability Checks ===

class CheckUsernameAvailabilityAPIView(View):
    """
    API view to check if a username is already taken.
    Expects a GET request with a 'value' query parameter.
    """
    def get(self, request, *args, **kwargs):
        username = request.GET.get('value', None)
        if username:
            exists = CustomUser.objects.filter(username__iexact=username).exists()
            return JsonResponse({'exists': exists})
        return JsonResponse({'error': 'Username parameter missing'}, status=400)

class CheckEmailAvailabilityAPIView(View):
    """
    API view to check if an email is already in use.
    Expects a GET request with a 'value' query parameter.
    """
    def get(self, request, *args, **kwargs):
        email = request.GET.get('value', None)
        if email:
            exists = CustomUser.objects.filter(email__iexact=email).exists()
            return JsonResponse({'exists': exists})
        return JsonResponse({'error': 'Email parameter missing'}, status=400)
