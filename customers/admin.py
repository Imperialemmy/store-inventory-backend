from django.contrib import admin
from .models import Customer, CustomerTag


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone_number", "city", "is_active")
    list_filter = ("is_active", "city")
    search_fields = ("name", "phone_number", "email")
    filter_horizontal = ("tags",)


@admin.register(CustomerTag)
class CustomerTagAdmin(admin.ModelAdmin):
    search_fields = ("name",)
