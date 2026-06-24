from django.contrib import admin
from .models import Sale, SaleItem, SaleItemAllocation, Payment


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "customer", "date", "total", "payment_status")
    list_filter = ("date", "customer__customer_type")
    search_fields = ("invoice_number", "customer__name")
    inlines = [SaleItemInline, PaymentInline]


admin.site.register(SaleItemAllocation)
admin.site.register(Payment)
