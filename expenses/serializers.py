from rest_framework import serializers
from .models import Expense, ExpenseCategory


class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = ["id", "name", "monthly_budget"]


class ExpenseSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    method_display = serializers.CharField(source="get_payment_method_display", read_only=True)
    receipt = serializers.FileField(use_url=True, required=False, allow_null=True)

    class Meta:
        model = Expense
        fields = [
            "id", "category", "category_name", "supplier", "supplier_name",
            "description", "amount", "payment_method", "method_display",
            "reference", "receipt", "date", "created_at",
        ]
        read_only_fields = ["created_at"]
