from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin 
from .models import CustomUser, UserDevice
from .forms import UserRegistrationForm, CustomUserChangeForm 
from django.utils.translation import gettext_lazy as _

class CustomUserAdmin(BaseUserAdmin):
    form = CustomUserChangeForm 
    add_form = UserRegistrationForm 

    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'borrower_id_value', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_superuser', 'is_active', 'groups', 'borrower_type')

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Personal info'), {'fields': (
            'first_name', 'last_name', 'middle_initial', 'suffix', 'email',
            'birth_date', 'phone_number', 'physical_address',
        )}),
        (_('Library Specific'), {'fields': (
            'role', 'borrower_id_label', 'borrower_id_value', 'borrower_type',
        )}),
        (_('Permissions'), {'fields': (
            'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'
        )}),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'username', 'email', 'password',
                'password2', 
                'first_name', 'last_name', 'middle_initial', 'suffix',
                'role', 'borrower_type', 'borrower_id_label', 'borrower_id_value',
            ),
        }),
    )
    search_fields = ('username', 'first_name', 'last_name', 'email', 'borrower_id_value')
    ordering = ('last_name', 'first_name', 'username')

admin.site.register(CustomUser, CustomUserAdmin)

@admin.register(UserDevice)
class UserDeviceAdmin(admin.ModelAdmin):
    list_display = ('user', 'registration_id_preview', 'is_active', 'date_created')
    list_filter = ('is_active', 'date_created')
    search_fields = ('user__username', 'registration_id')
    readonly_fields = ('date_created',)

    def registration_id_preview(self, obj):
        return obj.registration_id[:50] + '...' if len(obj.registration_id) > 50 else obj.registration_id
    registration_id_preview.short_description = _('Registration ID Preview')
