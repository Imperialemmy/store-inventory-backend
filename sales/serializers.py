from decimal import Decimal
from rest_framework import serializers
from inventory.models import WareVariant
from customers.models import Customer
from .models import Sale, SaleItem, Payment
from .services import create_sale


class SaleItemSerializer(serializers.ModelSerializer):
    variant = serializers.PrimaryKeyRelatedField(queryset=WareVariant.objects.all())
    variant_label = serializers.SerializerMethodField()
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = SaleItem
        fields = ["id", "variant", "variant_label", "quantity", "unit_price", "line_total"]
        extra_kwargs = {"unit_price": {"required": False}}

    def get_variant_label(self, obj):
        size = obj.variant.size
        return f"{obj.variant.ware.name} ({size})"


class PaymentSerializer(serializers.ModelSerializer):
    method_display = serializers.CharField(source="get_method_display", read_only=True)
    sale = serializers.PrimaryKeyRelatedField(queryset=Sale.objects.all())

    class Meta:
        model = Payment
        fields = ["id", "sale", "amount", "method", "method_display", "reference", "date", "created_at"]
        read_only_fields = ["created_at"]


class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True)
    payments = PaymentSerializer(many=True, read_only=True)
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all())
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    customer_type = serializers.CharField(source="customer.customer_type", read_only=True)
    salesperson = serializers.CharField(source="user.username", read_only=True)
    amount_paid = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    payment_status = serializers.CharField(read_only=True)

    class Meta:
        model = Sale
        fields = [
            "id", "invoice_number", "customer", "customer_name", "customer_type",
            "salesperson", "date", "discount", "vat_rate", "subtotal", "vat_amount",
            "total", "amount_paid", "balance", "payment_status", "notes",
            "items", "payments", "created_at",
        ]
        read_only_fields = [
            "invoice_number", "subtotal", "vat_amount", "total", "created_at",
        ]

    def create(self, validated_data):
        items = validated_data.pop("items")
        request = self.context.get("request")
        sale = create_sale(
            user=request.user if request else None,
            customer=validated_data["customer"],
            items=[
                {
                    "variant": item["variant"],
                    "quantity": item["quantity"],
                    "unit_price": item.get("unit_price"),
                }
                for item in items
            ],
            discount=validated_data.get("discount", Decimal("0")),
            vat_rate=validated_data.get("vat_rate"),
            date=validated_data.get("date"),
            notes=validated_data.get("notes"),
        )
        return sale
