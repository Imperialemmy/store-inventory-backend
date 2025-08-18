from django.db.models import Max
from rest_framework import serializers
from inventory.models import Brand, Category, Size, Ware, WareVariant, Batch, Image
from users.models import CustomUser
from django.db import transaction


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
    # variant_detail = WareVariantSerializer(source='variant', read_only=True)

    class Meta:
        model = Batch
        fields = ["id", "variant", "quantity", "expiry_date",
                  "manufacturing_date", "lot_number", "is_expired",'created_at','updated_at']
        read_only_fields = ["created_at", "updated_at"]

class WareVariantSerializer(serializers.ModelSerializer):
    ware = serializers.PrimaryKeyRelatedField(queryset=Ware.objects.all())
    size = serializers.PrimaryKeyRelatedField(queryset=Size.objects.all())  # Default queryset, overridden in create/update
    ware_name = serializers.CharField(source="ware.name", read_only=True)
    size_detail = SizeSerializer(source="size", read_only=True)  # Full size details for GET
    stock = serializers.SerializerMethodField()
    last_updated = serializers.SerializerMethodField()
    batches = BatchSerializer(many=True, read_only=True)

    class Meta:
        model = WareVariant
        fields = ["id", "ware", "ware_name", "size", "size_detail", "price", "is_available", "stock",'last_updated',"batches"]

    def get_stock(self, obj):
        return obj.get_stock()

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
        if value not in ("user", "admin"):
            raise serializers.ValidationError("Invalid role.")
        return value

    def update(self, instance, validated_data):
        with transaction.atomic():
            new_role = validated_data["role"]
            # Optional: prevent demoting the last admin
            if instance.role == "admin" and new_role == "user":
                if not CustomUser.objects.exclude(id=instance.id).filter(role="admin").exists():
                    raise serializers.ValidationError("Cannot demote the last admin.")
            instance.role = new_role
            # Keep is_staff in sync with role (but don't touch is_superuser here)
            instance.is_staff = (new_role == "admin")
            instance.save(update_fields=["role", "is_staff"])
            return instance