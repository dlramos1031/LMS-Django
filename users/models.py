from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings

class CustomUser(AbstractUser):
    full_name = models.CharField(max_length=255)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    
    ROLE_CHOICES = (
        ('user', 'Standard User'),
        ('admin', 'Admin/Librarian'),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='admin')

    def __str__(self):
        return self.username
    
    class Meta:
        ordering = ['full_name']

class UserDevice(models.Model):
    """
    Stores Expo Push Tokens associated with users.
    """
    # Link to the user account
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE, # Delete device record if user is deleted
        related_name='push_devices' # Optional: for easier reverse lookup
    )
    # The Expo Push Token string (e.g., ExponentPushToken[...])
    # Ensure unique=True to prevent duplicate tokens in the database
    device_token = models.CharField(max_length=255, unique=True)
    # Timestamp when the record was created
    created_at = models.DateTimeField(auto_now_add=True)

    # Flag to indicate if the token is currently considered valid/active
    # Defaults to True when a new device is registered.
    is_active = models.BooleanField(default=True)

    # Optional: Add a timestamp for the last update
    # updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Device"
        verbose_name_plural = "User Devices"
        # Optional: Add ordering if needed
        # ordering = ['-created_at']

    def __str__(self):
        """
        String representation for the admin interface and debugging.
        """
        # Truncate token for display brevity
        token_preview = f"{self.device_token[:20]}..." if self.device_token else "N/A"
        active_status = "Active" if self.is_active else "Inactive"
        # Safely access username (handle potential anonymous user if applicable)
        username = getattr(self.user, self.user.USERNAME_FIELD, 'N/A')
        return f"{username} - {token_preview} ({active_status})"
