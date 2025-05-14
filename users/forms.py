from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm, PasswordChangeForm
from .models import CustomUser
from django.utils.translation import gettext_lazy as _

class UserRegistrationForm(UserCreationForm):
    """
    Form for public user registration. Defaults role to BORROWER.
    """
    email = forms.EmailField(required=True, label=_("Email Address"))
    
    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = UserCreationForm.Meta.fields + ('email',)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = 'BORROWER'
        user.is_staff = False
        user.is_superuser = False
        if commit:
            user.save()
        return user


class BorrowerProfileUpdateForm(forms.ModelForm):
    """Form for Borrowers to update their own profile information."""
    class Meta:
        model = CustomUser
        fields = [
            'first_name',
            'last_name',
            'middle_initial',
            'suffix',
            'email',
            'borrower_id_value',
            'borrower_type',
            'physical_address',
            'birth_date',
            'phone_number',
            'profile_picture'
        ]
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date'}),
            'physical_address': forms.Textarea(attrs={'rows': 3}),
            'profile_picture': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'middle_initial': forms.TextInput(attrs={'class': 'form-control'}),
            'suffix': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'borrower_id_value': forms.TextInput(attrs={'class': 'form-control'}),
            'borrower_type': forms.Select(attrs={'class': 'form-select'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
        }
        help_texts = {
            'profile_picture': _('Upload a new profile picture. Clear to remove existing picture.'),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.borrower_id_value:
            self.fields['borrower_id_value'].disabled = True
            self.fields['borrower_id_value'].help_text = _("Your Library ID cannot be changed here. Contact support if needed.")


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


# ---------------------------- FOR STAFF DASHBOARD - USER MANAGEMENT ----------------------------

class StaffBaseUserForm(forms.ModelForm):
    """Base form for staff editing user details, excluding sensitive fields by default."""
    class Meta:
        model = CustomUser
        fields = [
            'username', 'first_name', 'last_name', 'middle_initial', 'suffix',
            'email', 'is_active',
            'borrower_id_label', 'borrower_id_value', 'borrower_type',
            'physical_address', 'birth_date', 'phone_number',
            'profile_picture'  # Added profile_picture here
        ]
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'physical_address': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'profile_picture': forms.ClearableFileInput(attrs={'class': 'form-control'}), # Added widget
            # Add other common widgets here if needed for consistency
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'middle_initial': forms.TextInput(attrs={'class': 'form-control'}),
            'suffix': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'borrower_id_label': forms.TextInput(attrs={'class': 'form-control'}),
            'borrower_id_value': forms.TextInput(attrs={'class': 'form-control'}),
            'borrower_type': forms.Select(attrs={'class': 'form-select'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
        }
        help_texts = {
            'profile_picture': _('Upload a new profile picture. Clear to remove existing picture.'),
        }

    def __init__(self, *args, **kwargs):
        self.requesting_user = kwargs.pop('requesting_user', None)
        super().__init__(*args, **kwargs)


class StaffBorrowerCreateForm(UserCreationForm):
    """Form for Staff (Librarians/Admins) to create new BORROWER accounts."""
    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=True)
    email = forms.EmailField(required=True)
    middle_initial = forms.CharField(max_length=10, required=False)
    suffix = forms.CharField(max_length=10, required=False)
    borrower_id_label = forms.CharField(max_length=50, required=False, initial="Library ID")
    borrower_id_value = forms.CharField(max_length=50, required=False)
    borrower_type = forms.ChoiceField(choices=CustomUser.BORROWER_TYPE_CHOICES, required=True)
    physical_address = forms.CharField(widget=forms.Textarea(attrs={'rows': 2}), required=False)
    birth_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}), required=False)
    phone_number = forms.CharField(max_length=20, required=False)
    is_active = forms.BooleanField(required=False, initial=True)
    profile_picture = forms.ImageField(required=False, widget=forms.ClearableFileInput(attrs={'class': 'form-control'}))


    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = UserCreationForm.Meta.fields + (
            'first_name', 'last_name', 'middle_initial', 'suffix', 'email',
            'borrower_id_label', 'borrower_id_value', 'borrower_type',
            'physical_address', 'birth_date', 'phone_number', 'is_active', 'profile_picture'
        )

    def __init__(self, *args, **kwargs):
        self.requesting_user = kwargs.pop('requesting_user', None)
        super().__init__(*args, **kwargs)
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = 'BORROWER'
        user.is_staff = False
        user.is_superuser = False
        if commit:
            user.save()
        return user


class StaffBorrowerChangeForm(StaffBaseUserForm):
    """Form for Staff (Librarians/Admins) to edit existing BORROWER accounts."""
    class Meta(StaffBaseUserForm.Meta):
        fields = StaffBaseUserForm.Meta.fields
        widgets = StaffBaseUserForm.Meta.widgets
        help_texts = StaffBaseUserForm.Meta.help_texts

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.requesting_user and self.requesting_user.role == 'LIBRARIAN' and not self.requesting_user.is_superuser:
            pass
        if self.instance and self.instance.pk:
            self.fields['username'].disabled = True
            if self.instance.role == 'BORROWER' and self.instance.borrower_id_value:
                 self.fields['borrower_id_value'].disabled = True
                 self.fields['borrower_id_value'].help_text = _("Borrower ID cannot be changed here. Contact support if needed.")


class AdminStaffCreateForm(UserCreationForm):
    """Form for ADMINS ONLY to create new STAFF accounts (Librarian or Admin)."""
    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=True)
    middle_initial = forms.CharField(max_length=10, required=False)
    suffix = forms.CharField(max_length=10, required=False)
    email = forms.EmailField(required=True)
    role = forms.ChoiceField(choices=[
        ('LIBRARIAN', _('Librarian')),
        ('ADMIN', _('Administrator')),
    ], required=True)
    is_active = forms.BooleanField(required=False, initial=True)
    is_staff = forms.BooleanField(required=False)
    is_superuser = forms.BooleanField(required=False)
    profile_picture = forms.ImageField(required=False, widget=forms.ClearableFileInput(attrs={'class': 'form-control'}))

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = UserCreationForm.Meta.fields + (
            'first_name', 'last_name', 'middle_initial', 'suffix', 'email', 'role', 'is_active', 'profile_picture',
            'is_staff', 'is_superuser'
        )
    
    def __init__(self, *args, **kwargs):
        self.requesting_user = kwargs.pop('requesting_user', None)
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        user = super().save(commit=False)
        selected_role = self.cleaned_data.get('role')
        user.role = selected_role
        if selected_role == 'ADMIN':
            user.is_staff = True
            user.is_superuser = True
        elif selected_role == 'LIBRARIAN':
            user.is_staff = True
            user.is_superuser = False
        if commit:
            user.save()
        return user


class AdminStaffChangeForm(StaffBaseUserForm):
    """Form for ADMINS ONLY to edit existing STAFF accounts."""
    role = forms.ChoiceField(choices=[ 
        ('LIBRARIAN', _('Librarian')),
        ('ADMIN', _('Administrator')),
    ], required=True)
    is_staff = forms.BooleanField(required=False)
    is_superuser = forms.BooleanField(required=False)

    class Meta(StaffBaseUserForm.Meta):
        model = CustomUser
        fields = [
            'username', 'first_name', 'last_name', 'middle_initial', 'suffix',
            'email', 'is_active', 'profile_picture',
            'role', 'is_staff', 'is_superuser'
        ]
        widgets = StaffBaseUserForm.Meta.widgets.copy()
        widgets.update({
            'role': forms.Select(attrs={'class': 'form-select'}),
            'is_staff': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_superuser': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        })

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['username'].disabled = True

            if self.requesting_user and self.instance.pk == self.requesting_user.pk:
                self.fields['role'].disabled = True
                self.fields['is_active'].disabled = True
                self.fields['is_staff'].disabled = True
                self.fields['is_superuser'].disabled = True
                self.fields['role'].help_text = _("You cannot change your own core administrative status.")

            if not (self.requesting_user and self.requesting_user.is_superuser):
                 self.fields['is_superuser'].disabled = True
                 if self.instance.role == 'ADMIN':
                     self.fields['role'].disabled = True
                 else:
                    self.fields['role'].choices = [('LIBRARIAN', _('Librarian'))]
                    if 'ADMIN' in dict(self.fields['role'].choices):
                        self.fields['role'].choices = [(val, disp) for val, disp in self.fields['role'].choices if val != 'ADMIN']


    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        is_staff = cleaned_data.get('is_staff')
        is_superuser = cleaned_data.get('is_superuser')

        if role == 'ADMIN':
            if not self.fields['is_staff'].disabled and not is_staff:
                self.add_error('is_staff', _("Administrators must also be staff members."))
            if not self.fields['is_superuser'].disabled and not is_superuser:
                self.add_error('is_superuser', _("Administrators must also be superusers."))
        elif role == 'LIBRARIAN':
            if not self.fields['is_staff'].disabled and not is_staff:
                self.add_error('is_staff', _("Librarians must also be staff members."))
            if not self.fields['is_superuser'].disabled and is_superuser:
                self.add_error('is_superuser', _("Librarians cannot be superusers. Assign Admin role for superuser status."))
        return cleaned_data
    