from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _

class CustomUser(AbstractUser):
    """
    Custom User model that extends Django's built-in AbstractUser.
    This model includes specific roles for the Library Management System (Borrower, Librarian, Admin)
    and additional information fields, especially for borrowers.
    """

    # Django's AbstractUser already provides:
    # username, email, password, first_name, last_name, 
    # is_staff (boolean, for admin site access), 
    # is_active (boolean, can login), 
    # date_joined.
    # This class will utilize the existing first_name and last_name fields.
    middle_initial = models.CharField(
        _('middle initial'), 
        max_length=10, 
        blank=True, 
        null=True, 
        help_text=_("User's middle initial (optional)")
    )
    suffix = models.CharField(
        _('suffix'), 
        max_length=10, 
        blank=True, 
        null=True, 
        help_text=_("e.g., Jr., Sr., III (optional)")
    )
    
    ROLE_CHOICES = (
        ('BORROWER', _('Borrower')),    # For students and other general library users
        ('LIBRARIAN', _('Librarian')),  # For library staff managing books and circulation
        ('ADMIN', _('Administrator')),  # For system administrators with full access
    )
    role = models.CharField(
        _('role'),
        max_length=20,
        choices=ROLE_CHOICES,
        default='BORROWER',
        help_text=_('The primary role of this user within the library system')
    )

    borrower_id_label = models.CharField(
        _('borrower ID label'),
        max_length=50, 
        default="Library ID",
        help_text=_("Label for the borrower's unique identifier (e.g., Student ID, Library Card No.)")
    )
    borrower_id_value = models.CharField(
        _('borrower ID value'),
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        help_text=_("The borrower's unique library identifier value (e.g., 'S12345', 'LC00789')")
    )
    physical_address = models.TextField(
        _('physical address'), 
        blank=True, 
        null=True,
        help_text=_("Borrower's physical mailing address (optional)")
    )
    birth_date = models.DateField(
        _('birth date'), 
        null=True, 
        blank=True,
        help_text=_("Borrower's date of birth (optional)")
    )
    phone_number = models.CharField(
        _('phone number'), 
        max_length=20,
        blank=True, 
        null=True,
        help_text=_("Borrower's contact phone number (optional)")
    )
    profile_picture = models.ImageField(
        _("Profile Picture"),
        upload_to='profile_pics/',
        blank=True,
        null=True,
        help_text=_("Upload a profile picture (optional).")
    )

    BORROWER_TYPE_CHOICES = (
        ('STUDENT', _('Student')),                  # Full-time students
        ('FACULTY', _('Faculty')),                  # Faculty members
        ('STAFF_MEMBER', _('Staff Member')),        # University staff (non-faculty) who are borrowers
        ('ALUMNI', _('Alumni')),                    # Former students who are still borrowers
        ('COMMUNITY', _('Community Member')),       # Other verified local borrowers
        ('OTHER', _('Other Verified Borrower')),    # Other verified borrowers (e.g., local residents, non-student/faculty)
    )
    borrower_type = models.CharField(
        _('borrower type'),
        max_length=30,
        choices=BORROWER_TYPE_CHOICES,
        null=True, 
        blank=True,
        help_text=_('Category of the borrower, e.g., Student, Faculty (used if role is Borrower)')
    )
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name=_('groups'),
        blank=True,
        help_text=_(
            'The groups this user belongs to. A user will get all permissions '
            'granted to each of their groups.'
        ),
        related_name="customuser_groups", 
        related_query_name="customuser",
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name=_('user permissions'),
        blank=True,
        help_text=_('Specific permissions for this user.'),
        related_name="customuser_permissions",
        related_query_name="customuser",
    )

    def get_full_name(self):
        """
        Returns the full name of the user, incorporating first name, middle initial, last name, and suffix.
        This overrides the default AbstractUser.get_full_name().
        """
        parts = [self.first_name]
        if self.middle_initial:
            parts.append(f"{self.middle_initial}.")
        parts.append(self.last_name)
        if self.suffix:
            parts.append(self.suffix)
        full_name = " ".join(filter(None, parts))
        return full_name.strip()

    def get_short_name(self):
        """
        Returns the short name for the user (typically the first name).
        This overrides the default AbstractUser.get_short_name().
        """
        return self.first_name

    def save(self, *args, **kwargs):
        if self.is_superuser and self.role != 'ADMIN':
            self.role = 'ADMIN'
        if self.is_staff and self.role == 'BORROWER':
            self.role = 'LIBRARIAN'
        super().save(*args, **kwargs)

    def __str__(self):
        """String representation of the CustomUser model."""
        return self.username

    class Meta:
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        ordering = ['last_name', 'first_name']

class UserDevice(models.Model):
    """
    Stores device tokens for push notifications, linking them to a CustomUser.
    This model is intended to work with a push notification setup like django-push-notifications.
    """
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE, 
        related_name='devices',
        help_text=_("The user this device token belongs to")
    )
    registration_id = models.TextField(
        unique=True,
        help_text=_("Push notification registration ID or token (e.g., FCM token)")
    )
    is_active = models.BooleanField(
        default=True, 
        help_text=_("Is this device currently active and should receive notifications?")
    )
    date_created = models.DateTimeField(
        auto_now_add=True,
        help_text=_("Date this device token was registered")
    )

    def __str__(self):
        """String representation of the UserDevice model."""
        token_preview = self.registration_id[:20] + '...' if len(self.registration_id) > 20 else self.registration_id
        return f"Device for {self.user.username} (Token: {token_preview})"

    class Meta:
        verbose_name = _('User Device')
        verbose_name_plural = _('User Devices')
        ordering = ['-date_created']