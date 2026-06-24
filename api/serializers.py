from django.db.models import Max
from rest_framework import serializers
from inventory.models import (
    Brand, Category, Size, Ware, WareVariant, Batch, Image,
    Supplier, Warehouse, AuditLog,
)
from customers.models import Customer, CustomerTag
from users.models import CustomUser
from django.db import transaction


class CustomerTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerTag
        fields = ["id", "name"]


class CustomerSerializer(serializers.ModelSerializer):
    # Read tags as full objects; write them as a list of names so the
    # client can simply send ["VIP", "Special Pricing"].
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


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = "__all__"


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = "__all__"


class AuditLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = AuditLog
        fields = ["id", "user", "username", "action", "model_name",
                  "object_id", "object_repr", "changes", "timestamp"]
        read_only_fields = fields


class CustomUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'phone_number','role']
        read_only_fields = ['id','role']
  
class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = "__all__"

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = "__all__"

class SizeSerializer(serializers.ModelSerializer):
    wares = serializers.SerializerMethodField()

    class Meta:
        model = Size
        fields = ['id', 'size', 'size_unit', 'wares']

    def get_wares(self, obj):
        return [
            {'id': ware.id, 'name': ware.name}
            for ware in obj.wares.all()
        ]
    


class BatchSerializer(serializers.ModelSerializer):
    variant = serializers.PrimaryKeyRelatedField(queryset=WareVariant.objects.all())
    warehouse = serializers.PrimaryKeyRelatedField(
        queryset=Warehouse.objects.all(), required=False, allow_null=True)
    supplier = serializers.PrimaryKeyRelatedField(
        queryset=Supplier.objects.all(), required=False, allow_null=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)

    class Meta:
        model = Batch
        fields = ["id", "variant", "warehouse", "warehouse_name", "supplier", "supplier_name",
                  "quantity", "expiry_date", "manufacturing_date", "lot_number",
                  "is_expired", 'created_at', 'updated_at']
        read_only_fields = ["created_at", "updated_at"]

class WareVariantSerializer(serializers.ModelSerializer):
    ware = serializers.PrimaryKeyRelatedField(queryset=Ware.objects.all())
    size = serializers.PrimaryKeyRelatedField(queryset=Size.objects.all())  # Default queryset, overridden in create/update
    ware_name = serializers.CharField(source="ware.name", read_only=True)
    size_detail = SizeSerializer(source="size", read_only=True)  # Full size details for GET
    stock = serializers.SerializerMethodField()
    stock_by_warehouse = serializers.SerializerMethodField()
    is_low_stock = serializers.BooleanField(read_only=True)
    last_updated = serializers.SerializerMethodField()
    batches = BatchSerializer(many=True, read_only=True)

    class Meta:
        model = WareVariant
        fields = ["id", "ware", "ware_name", "size", "size_detail", "price",
                  "reorder_point", "is_available", "stock", "stock_by_warehouse",
                  "is_low_stock", 'last_updated', "batches"]

    def get_stock(self, obj):
        return obj.get_stock()

    def get_stock_by_warehouse(self, obj):
        return obj.stock_by_warehouse()

    def validate(self, data):
        """
        Ensure the size chosen for the variant is one of the sizes linked to the ware.
        """
        ware = data.get("ware")
        size = data.get("size")
        if ware and size and size not in ware.size.all():
            raise serializers.ValidationError(
                f"Size {size} is not available for {ware.name}. Choose from: {', '.join(str(s) for s in ware.size.all())}"
            )
        return data

    def create(self, validated_data):
        """
        Create a WareVariant, ensuring size is from the ware's sizes.
        """
        return WareVariant.objects.create(**validated_data)

    def update(self, instance, validated_data):
        """
        Update a WareVariant, ensuring size is from the ware's sizes.
        """
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance

    def get_last_updated(self, obj):
        latest_batch = Batch.objects.filter(variant=obj).aggregate(Max('updated_at'))
        return latest_batch['updated_at__max']


class WareSerializer(serializers.ModelSerializer):
    brand = serializers.PrimaryKeyRelatedField(queryset=Brand.objects.all())
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all())
    size = serializers.PrimaryKeyRelatedField(queryset=Size.objects.all(), many=True)
    brand_detail = BrandSerializer(source='brand', read_only=True)
    category_detail = CategorySerializer(source='category', read_only=True)
    size_detail = SizeSerializer(source='size', many=True, read_only=True)
    variants = WareVariantSerializer(many=True, read_only=True)

    class Meta:
        model = Ware
        fields = ["id", "user", "name", "brand", "brand_detail", "category", "category_detail",
                  "description", "size", "size_detail", "created_at", "updated_at", "variants"]
        read_only_fields = ["user"]

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        sizes = validated_data.pop("size", [])
        ware = Ware.objects.create(**validated_data)
        ware.size.set(sizes)
        return ware

    def update(self, instance, validated_data):
        sizes = validated_data.pop("size", None)
        if sizes is not None:
            instance.size.set(sizes)
        return super().update(instance, validated_data)





class ImageSerializer(serializers.ModelSerializer):
    ware = serializers.PrimaryKeyRelatedField(queryset=Ware.objects.all())
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = Image
        fields = ["id", "ware", "image", "alt_text", "order"]


class PromoteUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ["role"]  # only allow changing role via this endpoint

    def validate_role(self, value):
        valid_roles = {choice[0] for choice in CustomUser.ROLE_CHOICES}
        if value not in valid_roles:
            raise serializers.ValidationError("Invalid role.")
        return value

    def update(self, instance, validated_data):
        with transaction.atomic():
            new_role = validated_data["role"]
            # Optional: prevent demoting the last admin
            if instance.role == "admin" and new_role != "admin":
                if not CustomUser.objects.exclude(id=instance.id).filter(role="admin").exists():
                    raise serializers.ValidationError("Cannot demote the last admin.")
            instance.role = new_role
            # Keep is_staff in sync with role (but don't touch is_superuser here)
            instance.is_staff = (new_role == "admin")
            instance.save(update_fields=["role", "is_staff"])
            return instance