from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.urls import reverse_lazy
from django.contrib.auth import login, get_user_model
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponseForbidden
from django.views.decorators.http import require_POST

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated

from books.models import Borrowing
from .serializers import RegisterSerializer
from .forms import UserRegistrationForm

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
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request.user.auth_token.delete()
        return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)

# ============================================
# 🌐 TEMPLATE-BASED VIEWS
# ============================================

def register_view(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST, request.FILES)
        print(form.is_valid())
        print(form.errors)  # Add this to see specific errors
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('books_list')
    else:
        form = UserRegistrationForm()
    return render(request, 'users/register.html', {'form': form})

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

@login_required
def user_profile_view(request, user_id):
    target_user = get_object_or_404(User, id=user_id)

    # Restrict access unless it's the user themselves or a staff member
    if request.user != target_user and not request.user.is_staff:
        return HttpResponseForbidden("You are not allowed to view this profile.")

    borrowings = Borrowing.objects.filter(user=target_user).order_by('-borrow_date')

    return render(request, 'users/profile.html', {
        'profile_user': target_user,
        'borrowings': borrowings
    })

@staff_member_required
@require_POST
def add_user_view(request):
    username = request.POST.get('username')
    full_name = request.POST.get('full_name')
    email = request.POST.get('email')
    password = request.POST.get('password')
    role = request.POST.get('role')

    user = User.objects.create_user(
        username=username,
        email=email,
        full_name=full_name,
        role=role,
        password=password
    )

    messages.success(request, "User added successfully.")
    return redirect('/dashboard/?tab=users')

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
    return redirect('/dashboard/?tab=users')

@staff_member_required
@require_POST
def delete_user_view(request, user_id):
    user = get_object_or_404(User, id=user_id)
    user.delete()
    messages.success(request, "User deleted successfully.")
    return redirect('/dashboard/?tab=users')
