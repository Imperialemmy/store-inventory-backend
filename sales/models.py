from decimal import Decimal
from django.db import models
from django.utils.timezone import now, localdate
from users.models import CustomUser
from customers.models import Customer
from inventory.models import WareVariant, Batch


class Sale(models.Model):
    """A sale / invoice raised for a customer."""
    PENDING = "pending"
    PARTIAL = "partial"
    PAID = "paid"

    user = models.ForeignKey(
        CustomUser, related_name="sales", on_delete=models.SET_NULL, null=True
    )
    customer = models.ForeignKey(Customer, related_name="sales", on_delete=models.PROTECT)
    invoice_number = models.CharField(max_length=30, unique=True, blank=True)
    date = models.DateField(default=localdate)

    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("7.5"))

    # Stored totals (recomputed from line items via recalculate()).
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.invoice_number or f"Sale #{self.pk}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.invoice_number:
            self.invoice_number = f"INV-{self.pk:05d}"
            super().save(update_fields=["invoice_number"])

    def recalculate(self, persist=True):
        """Recompute money totals from the current line items."""
        subtotal = sum((item.line_total for item in self.items.all()), Decimal("0"))
        taxable = max(subtotal - self.discount, Decimal("0"))
        vat_amount = (taxable * self.vat_rate / Decimal("100")).quantize(Decimal("0.01"))
        self.subtotal = subtotal
        self.vat_amount = vat_amount
        self.total = taxable + vat_amount
        if persist:
            super().save(update_fields=["subtotal", "vat_amount", "total", "updated_at"])

    @property
    def amount_paid(self):
        return self.payments.aggregate(total=models.Sum("amount"))["total"] or Decimal("0")

    @property
    def balance(self):
        return self.total - self.amount_paid

    @property
    def payment_status(self):
        paid = self.amount_paid
        if paid <= 0:
            return self.PENDING
        if paid >= self.total:
            return self.PAID
        return self.PARTIAL


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, related_name="items", on_delete=models.CASCADE)
    variant = models.ForeignKey(WareVariant, related_name="sale_items", on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.quantity} x {self.variant} @ {self.unit_price}"

    @property
    def line_total(self):
        return (self.unit_price or Decimal("0")) * self.quantity


class SaleItemAllocation(models.Model):
    """Records which batch a sale line drew stock from, so a deleted sale
    can return the exact quantities to the right batches."""
    sale_item = models.ForeignKey(SaleItem, related_name="allocations", on_delete=models.CASCADE)
    batch = models.ForeignKey(Batch, related_name="sale_allocations", on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()


class Payment(models.Model):
    CASH = "cash"
    TRANSFER = "transfer"
    POS = "pos"
    METHOD_CHOICES = (
        (CASH, "Cash"),
        (TRANSFER, "Bank Transfer"),
        (POS, "POS"),
    )

    sale = models.ForeignKey(Sale, related_name="payments", on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default=CASH)
    reference = models.CharField(max_length=100, blank=True, null=True)
    date = models.DateField(default=localdate)
    created_at = models.DateTimeField(default=now)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.amount} ({self.get_method_display()}) on {self.sale}"
