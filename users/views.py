from django.urls import reverse_lazy
from django.contrib import messages
from django.http import HttpResponseForbidden, JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth import login, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect, get_object_or_404

from rest_framework import status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated

from .decorators import redirect_authenticated_user
from .serializers import RegisterSerializer, UserProfileSerializer, UserDeviceSerializer
from .forms import UserRegistrationForm
from .models import UserDevice
from books.models import Borrowing
from books.views import _get_dashboard_context
from .decorators import admin_only

User = get_user_model()

# ============================================
# 🔐 API VIEWS
# ============================================

class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            token, created = Token.objects.get_or_create(user=user)
            return Response({
                "token": token.key,
                "user": {
                    "username": user.username,
                    "email": user.email,
                    "full_name": user.full_name,
                    "role": user.role,
                }
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CustomLoginView(ObtainAuthToken):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        token = Token.objects.get(key=response.data['token'])
        user = token.user
        return Response({
            "token": token.key,
            "user": {
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
            }
        })

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request.user.auth_token.delete()
        return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)

# ============================================
# 📱 MOBILE VIEWS
# ============================================

class UserProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

class RegisterDeviceView(generics.GenericAPIView): # Changed from CreateAPIView
    """
    Registers or updates a device token for the authenticated user.
    Uses update_or_create to handle both new and existing tokens idempotently.
    """
    serializer_class = UserDeviceSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        """
        Handles POST requests to register/update the device token.
        """
        # Validate the incoming data (expects 'device_token')
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True) # Raise validation error if token is missing/invalid

        device_token = serializer.validated_data['device_token']
        user = request.user

        # Use update_or_create to handle existing tokens gracefully
        # It finds a UserDevice by device_token.
        # If found, it updates the 'user' field to the current user.
        # If not found, it creates a new UserDevice with the token and user.
        try:
            device, created = UserDevice.objects.update_or_create(
                device_token=device_token,
                defaults={'user': user}
                # Note: Consider if you want to allow a token to be reassigned
                # from one user to another. This logic currently allows it.
                # If a token should ONLY belong to the first user who registered it,
                # you might need different logic (e.g., check if device exists
                # and belongs to a *different* user, then return 409 Conflict).
            )

            # Determine the appropriate response status code
            if created:
                status_code = status.HTTP_201_CREATED
                response_data = serializer.data # Return the data for the new device
                print(f"Device token CREATED for user {user.username}: {device_token}")
            else:
                # If the device was updated (or already existed with the correct user)
                status_code = status.HTTP_200_OK
                # Re-serialize the existing/updated device data to ensure consistency
                response_data = UserDeviceSerializer(instance=device).data
                print(f"Device token UPDATED/EXISTED for user {user.username}: {device_token}")

            # Return a success response with appropriate status and data
            return Response(response_data, status=status_code)

        except Exception as e:
            # Catch potential database errors or other issues
            print(f"Error during device registration for user {user.username}: {e}")
            return Response(
                {"error": "An internal error occurred during device registration."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# ============================================
# 🌐 TEMPLATE-BASED VIEWS
# ============================================

@method_decorator(redirect_authenticated_user, name='dispatch')
class CustomLoginViewWeb(LoginView):
    template_name = 'users/login.html'

    def get_success_url(self):
        user = self.request.user
        if user.role in ['librarian', 'admin']:
            return '/dashboard/'
        return '/books/'

@method_decorator(login_required, name='dispatch')
class CustomPasswordChangeView(PasswordChangeView):
    template_name = 'users/change_password.html'
    success_url = reverse_lazy('books_list')

@redirect_authenticated_user
def register_view(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = UserRegistrationForm()
    return render(request, 'users/register.html', {'form': form})

@login_required
def user_profile_view(request, user_id):
    target_user = get_object_or_404(User, id=user_id)

    if not request.user.is_staff and request.user != target_user:
        return HttpResponseForbidden("You are not allowed to view this profile.")

    borrowings = None
    if target_user.role == 'member':
        borrowings = Borrowing.objects.filter(user=target_user).order_by('-borrow_date')

    return render(request, 'users/profile.html', {
        'profile_user': target_user,
        'borrowings': borrowings
    })

@login_required
@require_POST
def edit_profile_view(request, user_id):
    user = get_object_or_404(User, id=user_id)

    user.username = request.POST.get('username')
    user.full_name = request.POST.get('full_name')
    user.email = request.POST.get('email')

    password = request.POST.get('password')
    if password:
        user.set_password(password)

    user.save()
    messages.success(request, "User updated successfully.")
    return redirect('user_profile', user_id=user.id)


@admin_only
def dashboard_users_view(request):
    active_tab_name = 'users'
    User = get_user_model()
    user_qs = User.objects.all() # Add filtering if needed (e.g., exclude superusers for non-superusers)
    context = _get_dashboard_context( # Use the same helper function
        request,
        active_tab_name,
        user_qs,
        search_fields=['username', 'full_name', 'email']
    )
    # Pass all users for modals if needed (similar to books)
    context['all_users'] = User.objects.all() # Adjust filter as needed
    return render(request, 'dashboard/users_section.html', context) # Use a specific template for users




@staff_member_required
@require_POST
def add_user_view(request):
    username = request.POST.get('username')
    full_name = request.POST.get('full_name')
    email = request.POST.get('email')
    password = request.POST.get('password')
    role = request.POST.get('role')

    User.objects.create_user(
        username=username,
        email=email,
        full_name=full_name,
        role=role,
        password=password
    )

    messages.success(request, "User added successfully.")
    return redirect('dashboard_users')

@staff_member_required
@require_POST
def edit_user_view(request, user_id):
    user = get_object_or_404(User, id=user_id)

    user.username = request.POST.get('username')
    user.full_name = request.POST.get('full_name')
    user.email = request.POST.get('email')
    user.role = request.POST.get('role')

    password = request.POST.get('password')
    if password:
        user.set_password(password)

    user.save()
    messages.success(request, "User updated successfully.")
    return redirect('dashboard_users')

@staff_member_required
@require_POST
def delete_user_view(request, user_id):
    user = get_object_or_404(User, id=user_id)
    user.delete()
    messages.success(request, "User deleted successfully.")
    return redirect('dashboard_users')

@require_GET
def check_username(request):
    username = request.GET.get('username', '').strip()
    exists = User.objects.filter(username__iexact=username).exists()
    return JsonResponse({'exists': exists})

@require_GET
def check_email(request):
    email = request.GET.get('email', '').strip()
    exists = User.objects.filter(email__iexact=email).exists()
    return JsonResponse({'exists': exists})