from rest_framework import serializers
from inventory.models import Product, AuditLog
from customers.models import Customer, CustomerTag
from users.models import CustomUser
from django.db import transaction


class ProductSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True, required=False, allow_null=True)

    class Meta:
        model = Product
        fields = ["id", "name", "image", "price", "stock", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]


class CustomUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'phone_number', 'role']
        read_only_fields = ['id', 'role']


class CustomerTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerTag
        fields = ["id", "name"]


class CustomerSerializer(serializers.ModelSerializer):
    tags = CustomerTagSerializer(many=True, read_only=True)
    tag_names = serializers.ListField(
        child=serializers.CharField(max_length=50), write_only=True, required=False
    )
    available_credit = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    customer_type_display = serializers.CharField(source="get_customer_type_display", read_only=True)

    class Meta:
        model = Customer
        fields = [
            "id", "name", "customer_type", "customer_type_display", "phone_number",
            "email", "address", "city", "credit_limit", "outstanding_balance",
            "available_credit", "tags", "tag_names", "notes", "is_active",
            "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def _resolve_tags(self, tag_names):
        tags = []
        for raw in tag_names:
            name = raw.strip()
            if not name:
                continue
            tag, _ = CustomerTag.objects.get_or_create(name=name)
            tags.append(tag)
        return tags

    def create(self, validated_data):
        tag_names = validated_data.pop("tag_names", None)
        validated_data["user"] = self.context["request"].user
        customer = Customer.objects.create(**validated_data)
        if tag_names is not None:
            customer.tags.set(self._resolve_tags(tag_names))
        return customer

    def update(self, instance, validated_data):
        tag_names = validated_data.pop("tag_names", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if tag_names is not None:
            instance.tags.set(self._resolve_tags(tag_names))
        return instance


class AuditLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = AuditLog
        fields = ["id", "user", "username", "action", "model_name",
                  "object_id", "object_repr", "changes", "timestamp"]
        read_only_fields = fields


class PromoteUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ["role"]

    def validate_role(self, value):
        valid_roles = {choice[0] for choice in CustomUser.ROLE_CHOICES}
        if value not in valid_roles:
            raise serializers.ValidationError("Invalid role.")
        return value

    def update(self, instance, validated_data):
        with transaction.atomic():
            new_role = validated_data["role"]
            if instance.role == "admin" and new_role != "admin":
                if not CustomUser.objects.exclude(id=instance.id).filter(role="admin").exists():
                    raise serializers.ValidationError("Cannot demote the last admin.")
            instance.role = new_role
            instance.is_staff = (new_role == "admin")
            instance.save(update_fields=["role", "is_staff"])
            return instance
