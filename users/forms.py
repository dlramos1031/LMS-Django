from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm, PasswordChangeForm
from .models import CustomUser
from django.utils.translation import gettext_lazy as _

class UserRegistrationForm(UserCreationForm):
    """
    A form for creating new users. Includes all the required
    fields, plus a repeated password, and new detailed name fields.
    """
    first_name = forms.CharField(max_length=150, required=True, label=_("First Name"))
    last_name = forms.CharField(max_length=150, required=True, label=_("Last Name"))
    middle_initial = forms.CharField(max_length=10, required=False, label=_("Middle Initial"))
    suffix = forms.CharField(max_length=10, required=False, label=_("Suffix (e.g., Jr., Sr.)"))
    email = forms.EmailField(required=True, label=_("Email Address"))

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = UserCreationForm.Meta.fields + ( # username is in UserCreationForm.Meta.fields
            'first_name',
            'last_name',
            'middle_initial',
            'suffix',
            'email'
            # password and password2 are implicitly inherited from UserCreationForm's structure
        )
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'role' in self.fields and not self.initial.get('role'):
            self.fields['role'].initial = 'BORROWER'
        
        if 'email' in self.fields:
            self.fields['email'].required = True

    def save(self, commit=True):
        user = super().save(commit=False)
        if not user.role:
            user.role = 'BORROWER'
        if commit:
            user.save()
        return user


class CustomUserChangeForm(UserChangeForm):
    """
    A form for updating users, typically used in the Django admin.
    Includes all the fields on the user, but replaces the password field
    with admin's password hash display.
    """
    first_name = forms.CharField(max_length=150, required=False, label=_("First Name"))
    last_name = forms.CharField(max_length=150, required=False, label=_("Last Name"))
    middle_initial = forms.CharField(max_length=10, required=False, label=_("Middle Initial"))
    suffix = forms.CharField(max_length=10, required=False, label=_("Suffix"))
    email = forms.EmailField(required=False, label=_("Email Address"))

    borrower_id_label = forms.CharField(max_length=50, required=False, label=_("Borrower ID Label"))
    borrower_id_value = forms.CharField(max_length=50, required=False, label=_("Borrower ID Value"))
    physical_address = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False, label=_("Physical Address"))
    birth_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}), required=False, label=_("Birth Date"))
    phone_number = forms.CharField(max_length=20, required=False, label=_("Phone Number"))
    
    borrower_type = forms.ChoiceField(choices=CustomUser.BORROWER_TYPE_CHOICES, required=False, label=_("Borrower Type"))
    role = forms.ChoiceField(choices=CustomUser.ROLE_CHOICES, required=True, label=_("Role"))

    class Meta(UserChangeForm.Meta):
        model = CustomUser
        fields = (
            'username',
            'email',
            'first_name',
            'last_name',
            'middle_initial',
            'suffix',
            'role',
            'borrower_id_label',
            'borrower_id_value',
            'physical_address',
            'birth_date',
            'phone_number',
            'borrower_type',
            'is_active',
            'is_staff',
            'is_superuser',
            'groups',
            'user_permissions',
            'last_login',
            'date_joined',
        )


class CustomPasswordChangeForm(PasswordChangeForm):
    """ Custom password change form. """
    pass

class BorrowerProfileUpdateForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150, required=True, label=_("First Name"))
    last_name = forms.CharField(max_length=150, required=True, label=_("Last Name"))
    middle_initial = forms.CharField(max_length=10, required=False, label=_("Middle Initial"))
    suffix = forms.CharField(max_length=10, required=False, label=_("Suffix"))
    email = forms.EmailField(required=True, label=_("Email Address"))
    physical_address = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False, label=_("Physical Address"))
    birth_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}), required=False, label=_("Birth Date"))
    phone_number = forms.CharField(max_length=20, required=False, label=_("Phone Number"))

    class Meta:
        model = CustomUser
        fields = [
            'first_name', 
            'last_name', 
            'middle_initial', 
            'suffix', 
            'email',
            'physical_address',
            'birth_date',
            'phone_number',
        ]
