from django.contrib.auth.models import AbstractUser
from django.db import models

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
