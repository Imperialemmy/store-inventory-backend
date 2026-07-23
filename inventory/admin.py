from django.contrib import admin
from .models import Product, AuditLog


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "stock")
    list_filter = ("category",)
    search_fields = ("name",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "user", "action", "model_name", "object_id", "object_repr")
    list_filter = ("action", "model_name")
    search_fields = ("object_repr", "object_id")
    readonly_fields = ("user", "action", "model_name", "object_id", "object_repr", "changes", "timestamp")
