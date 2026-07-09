from django.conf import settings
from django.db import transaction
from djoser.serializers import UserCreateSerializer as BaseUserCreateSerializer
from djoser.serializers import UserSerializer as BaseUserSerializer
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import CustomUser


class CustomUserCreateSerializer(BaseUserCreateSerializer):
    """Registration (POST /auth/users/).

    - A correct `admin_code` (matching settings.ADMIN_SIGNUP_CODE) creates an
      active admin. So does the very first account ever (bootstrap).
    - Everyone else becomes a Seller whose account is inactive until an admin
      approves it — Django/JWT refuse login for inactive users.
    """
    admin_code = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta(BaseUserCreateSerializer.Meta):
        model = CustomUser
        fields = ('id', 'username', 'first_name', 'last_name', 'email',
                  'password', 'phone_number', 'admin_code')
        extra_kwargs = {'password': {'write_only': True}}

    def validate(self, attrs):
        # Pull admin_code out before djoser builds a User(**attrs) for its own
        # password validation (it would choke on the non-model field).
        self._admin_code = attrs.pop('admin_code', '')
        return super().validate(attrs)

    def create(self, validated_data):
        admin_code = (getattr(self, '_admin_code', '') or '').strip()
        configured = (getattr(settings, 'ADMIN_SIGNUP_CODE', '') or '').strip()

        with transaction.atomic():
            is_first_user = CustomUser.objects.select_for_update().count() == 0
            wants_admin = bool(admin_code)

            if wants_admin and not (configured and admin_code == configured):
                raise serializers.ValidationError({"admin_code": "Invalid admin code."})

            becomes_admin = is_first_user or (configured and admin_code == configured)

            user = super().create(validated_data)  # hashes the password
            if becomes_admin:
                user.role = CustomUser.ADMIN
                user.is_staff = True
                user.is_active = True
                if is_first_user:
                    user.is_superuser = True
                user.save(update_fields=["role", "is_staff", "is_active", "is_superuser"])
            else:
                user.role = CustomUser.SELLER
                user.is_active = False  # pending admin approval
                user.save(update_fields=["role", "is_active"])
        return user


class CustomUserSerializer(BaseUserSerializer):
    """Current-user info (GET /auth/users/me/)."""
    class Meta(BaseUserSerializer.Meta):
        model = CustomUser
        fields = ('id', 'username', 'first_name', 'last_name', 'email', 'phone_number', 'role')


class UserAdminSerializer(serializers.ModelSerializer):
    """Read model for the admin Team screen."""
    class Meta:
        model = CustomUser
        fields = ('id', 'username', 'first_name', 'last_name', 'email',
                  'phone_number', 'role', 'is_active', 'date_joined')
        read_only_fields = fields


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['role'] = user.role
        return token
