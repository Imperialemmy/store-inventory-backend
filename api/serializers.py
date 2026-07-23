from rest_framework import serializers
from inventory.models import Product, InventoryMovement
from customers.models import Customer, CustomerTag


class ProductSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True, required=False, allow_null=True)

    class Meta:
        model = Product
        fields = [
            "id", "name", "category", "image", "price", "cost_price", "stock",
            "reorder_level", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate_name(self, value):
        # Trim and treat names case-insensitively so "Rice", "rice " and
        # "RICE" can't become three separate products.
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Name is required.")
        clashes = Product.objects.filter(name__iexact=value)
        if self.instance:
            clashes = clashes.exclude(pk=self.instance.pk)
        if clashes.exists():
            raise serializers.ValidationError("A product with this name already exists.")
        return value


class CustomerTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerTag
        fields = ["id", "name"]


class CustomerSerializer(serializers.ModelSerializer):
    # Tags are managed through the customer itself: read as objects, write
    # as a list of names (created on the fly).
    tags = CustomerTagSerializer(many=True, read_only=True)
    tag_names = serializers.ListField(
        child=serializers.CharField(max_length=50), write_only=True, required=False
    )

    class Meta:
        model = Customer
        fields = [
            "id", "name", "phone_number",
            "email", "address", "city",
            "tags", "tag_names", "notes", "is_active",
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


class InventoryMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    user_name = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = InventoryMovement
        fields = [
            "id", "product", "product_name", "sale", "user_name", "quantity",
            "stock_after", "reason", "client_reference", "device_id",
            "event_at", "synced_at", "note", "created_at",
        ]
        read_only_fields = [
            "sale", "user_name", "stock_after", "client_reference", "device_id",
            "synced_at", "created_at",
        ]
