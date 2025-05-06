from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import UserDevice

User = get_user_model()

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'full_name', 'email', 'password', 'confirm_password']

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError("Passwords do not match.")
        return data

    def create(self, validated_data):
        validated_data.pop('confirm_password')
        user = User.objects.create_user(
            username=validated_data['username'],
            full_name=validated_data.get('full_name', ''),
            email=validated_data.get('email', ''),
            password=validated_data['password'],
        )
        user.role = 'member'
        user.save()
        return user

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'full_name', 'email', 'role']
        read_only_fields = ['username', 'email', 'role', 'id']
        
class UserDeviceSerializer(serializers.ModelSerializer):
    """
    Serializer for the UserDevice model.
    Disables default uniqueness validation for device_token,
    as uniqueness is handled in the RegisterDeviceView using update_or_create.
    """
    class Meta:
        model = UserDevice
        fields = [
            'device_token',
            # Include 'user' if you want it in the response, mark as read-only
            # 'user',
            # Include 'id' if you want it in the response
            # 'id',
        ]
        extra_kwargs = {
            'device_token': {
                # Override default validators, removing the UniqueValidator
                'validators': [],
            },
            # If including user in fields, make it read-only in requests
            # 'user': {'read_only': True},
        }