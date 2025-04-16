import re
from django import forms
from django.core.exceptions import ValidationError
from .models import CustomUser

class UserRegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = CustomUser
        fields = ['username', 'full_name', 'email']

    def clean_username(self):
        username = self.cleaned_data.get('username')

        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            raise ValidationError("Username can only contain letters, numbers, and underscores.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        
        if not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
            raise ValidationError("Enter a valid email address.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', 'Passwords do not match')

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        user.role = 'member'
        if commit:
            user.save()
        return user
