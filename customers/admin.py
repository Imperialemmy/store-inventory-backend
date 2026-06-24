from django.contrib import admin
from .models import Customer, CustomerTag


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "customer_type", "phone_number", "city", "outstanding_balance", "credit_limit", "is_active")
    list_filter = ("customer_type", "is_active", "city")
    search_fields = ("name", "phone_number", "email")
    filter_horizontal = ("tags",)


@admin.register(CustomerTag)
class CustomerTagAdmin(admin.ModelAdmin):
    search_fields = ("name",)
