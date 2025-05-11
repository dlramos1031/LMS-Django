from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import login, get_user_model, authenticate, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404

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

User = get_user_model()


# === Django Template-Rendering Views ===

def user_register_view(request):
    if request.user.is_authenticated:
        return redirect('books:portal_book_list')

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
    return render(request, 'users/register.html', {'form': form, 'page_title': _('Register')})


def user_login_view(request):
    if request.user.is_authenticated:
        return redirect('books:portal_book_list')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, _('Login successful.'))
            if user.role == 'ADMIN' or user.role == 'LIBRARIAN':
                return redirect('books:staff_dashboard_home') 
            else:
                return redirect('books:portal_book_list')
        else:
            messages.error(request, _('Invalid username or password.'))
    return render(request, 'users/login.html', {'page_title': _('Login')})


@login_required
def user_logout_view(request):
    logout(request)
    messages.info(request, _('You have been successfully logged out.'))
    return redirect('users:login')


@login_required
def user_profile_view(request):
    user = get_object_or_404(CustomUser, pk=request.user.pk)
    context = {
        'user_profile': user,
        'page_title': _('My Profile')
    }
    return render(request, 'users/profile.html', context)

@login_required
def user_profile_edit_view(request):
    if request.method == 'POST':
        form = BorrowerProfileUpdateForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, _('Your profile has been updated successfully.'))
            return redirect('users:profile')
    else:
        form = BorrowerProfileUpdateForm(instance=request.user)
    
    context = {
        'form': form,
        'page_title': _('Edit Profile')
    }
    return render(request, 'users/profile_edit.html', context)


@login_required
def change_password_view(request):
    if request.method == 'POST':
        form = CustomPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, _('Your password was successfully updated!'))
            return redirect('users:profile')
        else:
            pass
    else:
        form = CustomPasswordChangeForm(request.user)
    return render(request, 'users/change_password.html', {
        'form': form,
        'page_title': _('Change Password')
    })


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
            # Delete the token to force a logout
            request.user.auth_token.delete()
        except (AttributeError, Token.DoesNotExist):
            pass # User might not have a token or already logged out
        return Response({"detail": _("Successfully logged out.")}, status=status.HTTP_200_OK)


class UserProfileAPIView(generics.RetrieveUpdateAPIView):
    """ API view for retrieving and updating user profile """
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class ChangePasswordAPIView(generics.UpdateAPIView):
    """ API view for changing password """
    serializer_class = ChangePasswordSerializer
    model = CustomUser
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, queryset=None):
        return self.request.user

    def update(self, request, *args, **kwargs):
        self.object = self.get_object()
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            # Check old password
            if not self.object.check_password(serializer.data.get("old_password")):
                return Response({"old_password": [_("Wrong password.")]}, status=status.HTTP_400_BAD_REQUEST)
            # set_password hashes the password
            self.object.set_password(serializer.data.get("new_password"))
            self.object.save()
            # Update session auth hash if session auth is also used
            # update_session_auth_hash(request, self.object) # Not typical for token auth
            return Response({"detail": _("Password changed successfully.")}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# Password Reset API Views (using django-rest-passwordreset)
# These typically don't need to be custom written if the library provides them.
# If you are using django-rest-passwordreset, you include its URLs in your project's urls.py.
# The CustomPasswordResetSerializer and CustomPasswordResetConfirmSerializer
# would be used if you are customizing the behavior of django-rest-passwordreset.

class UserDeviceViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing user devices for push notifications.
    """
    queryset = UserDevice.objects.all()
    serializer_class = UserDeviceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Users can only manage their own devices."""
        return UserDevice.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        """Associate the device with the current authenticated user."""
        # Check if a device with this registration_id already exists for this user or another
        registration_id = serializer.validated_data.get('registration_id')
        existing_device = UserDevice.objects.filter(registration_id=registration_id).first()
        if existing_device:
            if existing_device.user == self.request.user:
                # Update existing device for this user (e.g., mark as active)
                existing_device.is_active = True 
                existing_device.save()
                # To prevent DRF from trying to create a new one, you might want to
                # return the existing one or handle this in the serializer's create method.
                # For simplicity here, we'll let it potentially error on unique constraint
                # if not handled by serializer or if a different user has this token.
                # A better approach is to update_or_create.
                UserDevice.objects.update_or_create(
                    user=self.request.user, 
                    registration_id=registration_id,
                    defaults={'is_active': True} # Add other fields to update if needed
                )
                # Since update_or_create handles it, we don't call serializer.save() directly in this case
                # We need to return a response consistent with creation though.
                # This logic is better placed in the serializer's create or validate method.
                # For now, let's assume the unique constraint on registration_id handles conflicts.
                serializer.save(user=self.request.user, is_active=True) # Simplistic save
            else:
                # This token is registered to another user. This shouldn't happen if tokens are unique.
                raise serializers.ValidationError(_("This device token is already registered to another user."))
        else:
            serializer.save(user=self.request.user)
