from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from .models import UserDevice

CustomUser = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for the CustomUser model (general purpose, e.g., for profile).
    """
    full_name = serializers.CharField(source='get_full_name', read_only=True)

    class Meta:
        model = CustomUser
        fields = (
            'id', 'username', 'email', 
            'first_name', 'last_name', 'middle_initial', 'suffix', 'full_name',
            'role', 'borrower_id_label', 'borrower_id_value', 'profile_picture',
            'physical_address', 'birth_date', 'phone_number', 'borrower_type', 
            'date_joined', 'last_login', 'is_active'
        )
        read_only_fields = ('role', 'date_joined', 'last_login', 'is_active')

class RegisterSerializer(serializers.ModelSerializer):
    """
    Serializer specifically for user registration via API.
    Handles password confirmation and creation of a new CustomUser.
    """
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'}, label=_("Password"))
    password2 = serializers.CharField(write_only=True, required=True, label=_("Confirm password"), style={'input_type': 'password'})
    
    first_name = serializers.CharField(required=True, max_length=150)
    last_name = serializers.CharField(required=True, max_length=150)
    email = serializers.EmailField(required=True)

    class Meta:
        model = CustomUser
        fields = (
            'username', 'password', 'password2', 'email', 
            'first_name', 'last_name', 'middle_initial', 'suffix',
        )
        extra_kwargs = {
            'middle_initial': {'required': False, 'allow_blank': True, 'max_length': 10},
            'suffix': {'required': False, 'allow_blank': True, 'max_length': 10},
        }

    def validate_email(self, value):
        if CustomUser.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(_("This email address is already in use."))
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password2": _("Password fields didn't match.")})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        user = CustomUser.objects.create_user(
            username=validated_data['username'],
            password=validated_data['password'],
            email=validated_data.get('email', ''),
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            middle_initial=validated_data.get('middle_initial'),
            suffix=validated_data.get('suffix'),
            role='BORROWER' 
        )
        return user

class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer for password change endpoint. Requires old password and new password confirmation.
    """
    old_password = serializers.CharField(required=True, style={'input_type': 'password'})
    new_password = serializers.CharField(required=True, style={'input_type': 'password'})
    confirm_new_password = serializers.CharField(required=True, label=_("Confirm new password"), style={'input_type': 'password'})

    def validate_new_password(self, value):
        # from django.contrib.auth.password_validation import validate_password
        # try:
        #     validate_password(value)
        # except forms.ValidationError as e: 
        #     raise serializers.ValidationError(e.messages)
        return value

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_new_password']:
            raise serializers.ValidationError({"new_password": _("New password fields didn't match.")})
        return attrs

class UserDeviceSerializer(serializers.ModelSerializer):
    """
    Serializer for UserDevice model.
    """
    class Meta:
        model = UserDevice
        fields = ['id', 'registration_id', 'is_active', 'date_created', 'user']
        read_only_fields = ('user', 'date_created')