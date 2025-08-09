from djoser.serializers import UserCreateSerializer as BaseUserCreateSerializer
from django.utils.translation import gettext_lazy as _
from djoser.serializers import UserSerializer as BaseUserSerializer
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import CustomUser
from django.db import transaction

# Used during registration (POST /auth/users/)
class CustomUserCreateSerializer(BaseUserCreateSerializer):
    class Meta(BaseUserCreateSerializer.Meta):
        model = CustomUser
        fields = ('id', 'username','first_name','last_name', 'email', 'password', 'phone_number')
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        # Avoid race conditions if two people sign up at the same time
        with transaction.atomic():
            is_first_user = CustomUser.objects.select_for_update().count() == 0
            user = super().create(validated_data)  # uses create_user, hashes password

            if is_first_user:
                user.role = "admin"
                user.is_staff = True
                user.is_superuser = True
                user.save(update_fields=["role", "is_staff", "is_superuser"])
        return user

# Used when retrieving user info (GET /auth/users/me/)
class CustomUserSerializer(BaseUserSerializer):
    class Meta(BaseUserSerializer.Meta):
        model = CustomUser
        fields = ('id', 'username','first_name','last_name', 'email', 'phone_number','role')


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Add custom claims
        token['username'] = user.username
        token['role'] = user.role  # 👈 Make sure your User model has this field

        return token