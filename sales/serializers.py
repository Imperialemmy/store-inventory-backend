from decimal import Decimal
from rest_framework import serializers
from inventory.models import Product
from customers.models import Customer
from .models import Sale, SaleItem, Payment, Refund, CreditNote, CreditNoteItem
from .services import create_sale, create_credit_note, create_refund, credited_quantity


class SaleItemSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    product_name = serializers.CharField(source="product.name", read_only=True)
    quantity = serializers.DecimalField(
        max_digits=14, decimal_places=4, coerce_to_string=False
    )
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    returned_quantity = serializers.SerializerMethodField()

    class Meta:
        model = SaleItem
        fields = ["id", "product", "product_name", "quantity", "unit_price",
                  "line_total", "returned_quantity"]
        extra_kwargs = {"unit_price": {"required": False}}

    def get_returned_quantity(self, obj):
        return credited_quantity(obj)


class PaymentSerializer(serializers.ModelSerializer):
    method_display = serializers.CharField(source="get_method_display", read_only=True)
    sale = serializers.PrimaryKeyRelatedField(queryset=Sale.objects.all())

    class Meta:
        model = Payment
        fields = ["id", "sale", "amount", "method", "method_display", "reference", "date", "created_at"]
        read_only_fields = ["created_at"]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Payment amount must be greater than zero.")
        return value

    def validate(self, attrs):
        sale = attrs.get("sale")
        amount = attrs.get("amount")
        if sale and amount and amount > sale.receivable:
            raise serializers.ValidationError(
                {"amount": "Payment cannot be greater than the outstanding balance."}
            )
        return attrs


class RefundSerializer(serializers.ModelSerializer):
    method_display = serializers.CharField(source="get_method_display", read_only=True)
    sale = serializers.PrimaryKeyRelatedField(queryset=Sale.objects.all())
    recorded_by = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = Refund
        fields = [
            "id", "sale", "amount", "method", "method_display", "reference",
            "date", "recorded_by", "created_at",
        ]
        read_only_fields = ["date", "recorded_by", "created_at"]

    def create(self, validated_data):
        request = self.context.get("request")
        return create_refund(
            sale=validated_data["sale"],
            amount=validated_data["amount"],
            method=validated_data.get("method", Refund.CASH),
            reference=validated_data.get("reference"),
            user=request.user if request else None,
        )


class CreditNoteItemSerializer(serializers.ModelSerializer):
    sale_item = serializers.PrimaryKeyRelatedField(queryset=SaleItem.objects.all())
    product_name = serializers.CharField(source="sale_item.product.name", read_only=True)
    quantity = serializers.DecimalField(
        max_digits=14, decimal_places=4, coerce_to_string=False
    )

    class Meta:
        model = CreditNoteItem
        fields = ["id", "sale_item", "product_name", "quantity", "unit_price"]
        read_only_fields = ["unit_price"]


class CreditNoteSerializer(serializers.ModelSerializer):
    items = CreditNoteItemSerializer(many=True)
    sale = serializers.PrimaryKeyRelatedField(queryset=Sale.objects.all())
    invoice_number = serializers.CharField(source="sale.invoice_number", read_only=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = CreditNote
        fields = ["id", "sale", "invoice_number", "reason", "amount", "items", "created_at"]
        read_only_fields = ["created_at"]

    def create(self, validated_data):
        items = validated_data.pop("items")
        request = self.context.get("request")
        return create_credit_note(
            sale=validated_data["sale"],
            items=[{"sale_item": i["sale_item"], "quantity": i["quantity"]} for i in items],
            user=request.user if request else None,
            reason=validated_data.get("reason"),
        )


class SaleSerializer(serializers.ModelSerializer):
    client_sale_id = serializers.UUIDField(required=False)
    items = SaleItemSerializer(many=True)
    payments = PaymentSerializer(many=True, read_only=True)
    refunds = RefundSerializer(many=True, read_only=True)
    credit_notes = CreditNoteSerializer(many=True, read_only=True)
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all())
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    salesperson = serializers.CharField(source="user.username", read_only=True)
    amount_paid = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    amount_credited = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    amount_refunded = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    net_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    receivable = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    refund_due = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    return_status = serializers.CharField(read_only=True)
    payment_status = serializers.CharField(read_only=True)
    initial_payment = serializers.DictField(write_only=True, required=False)

    class Meta:
        model = Sale
        fields = [
            "id", "client_sale_id", "invoice_number", "customer", "customer_name",
            "salesperson", "date", "discount", "vat_rate", "subtotal", "vat_amount",
            "total", "amount_paid", "amount_credited", "amount_refunded",
            "net_total", "receivable",
            "refund_due", "balance", "payment_status", "return_status", "notes",
            "items", "payments", "refunds", "credit_notes", "sold_at", "synced_at", "device_id",
            "offline_created", "inventory_attention", "pricing_attention",
            "inventory_resolution", "inventory_resolution_note",
            "inventory_resolved_by", "inventory_resolved_at",
            "initial_payment", "created_at",
        ]
        read_only_fields = [
            "invoice_number", "subtotal", "vat_amount", "total", "synced_at",
            "inventory_attention", "pricing_attention", "created_at",
            "inventory_resolution", "inventory_resolution_note",
            "inventory_resolved_by", "inventory_resolved_at",
        ]
        extra_kwargs = {
            "client_sale_id": {"validators": []},
        }

    def create(self, validated_data):
        items = validated_data.pop("items")
        payment = validated_data.pop("initial_payment", None)
        request = self.context.get("request")
        sale, _ = create_sale(
            user=request.user if request else None,
            customer=validated_data["customer"],
            items=[
                {"product": item["product"], "quantity": item["quantity"], "unit_price": item.get("unit_price")}
                for item in items
            ],
            discount=validated_data.get("discount", Decimal("0")),
            vat_rate=validated_data.get("vat_rate"),
            date=validated_data.get("date"),
            notes=validated_data.get("notes"),
            client_sale_id=validated_data.get("client_sale_id"),
            sold_at=validated_data.get("sold_at"),
            device_id=validated_data.get("device_id"),
            offline_created=validated_data.get("offline_created", False),
            payment=payment,
        )
        return sale
