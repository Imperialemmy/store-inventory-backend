from django.contrib import admin
from .models import Sale, SaleItem, Payment, Refund, CreditNote, CreditNoteItem


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0


class RefundInline(admin.TabularInline):
    model = Refund
    extra = 0


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "customer", "date", "total", "payment_status")
    list_filter = ("date",)
    search_fields = ("invoice_number", "customer__name")
    inlines = [SaleItemInline, PaymentInline, RefundInline]


admin.site.register(CreditNote)
admin.site.register(CreditNoteItem)
admin.site.register(Payment)
admin.site.register(Refund)
