from django.contrib import admin
from .models import (
    Brand, Category, Size, Ware, WareVariant, Batch, Image,
    Supplier, Warehouse, AuditLog,
)

admin.site.register(Brand)
admin.site.register(Category)
admin.site.register(Size)
admin.site.register(Ware)
admin.site.register(WareVariant)
admin.site.register(Batch)
admin.site.register(Image)
admin.site.register(Supplier)
admin.site.register(Warehouse)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "user", "action", "model_name", "object_id", "object_repr")
    list_filter = ("action", "model_name")
    search_fields = ("object_repr", "object_id")
    readonly_fields = ("user", "action", "model_name", "object_id", "object_repr", "changes", "timestamp")
