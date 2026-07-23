from decimal import Decimal
from django.db import models
from django.utils.timezone import now, localdate
import uuid
from users.models import CustomUser
from customers.models import Customer
from inventory.models import Product


class Sale(models.Model):
    """A sale / invoice raised for a customer."""
    PENDING = "pending"
    PARTIAL = "partial"
    PAID = "paid"
    RETURN_NONE = "none"
    RETURN_PARTIAL = "partial"
    RETURN_FULL = "full"

    user = models.ForeignKey(
        CustomUser, related_name="sales", on_delete=models.SET_NULL, null=True
    )
    customer = models.ForeignKey(Customer, related_name="sales", on_delete=models.PROTECT)
    client_sale_id = models.UUIDField(
        unique=True, default=uuid.uuid4, editable=False, db_index=True
    )
    invoice_number = models.CharField(max_length=30, unique=True, blank=True)
    date = models.DateField(default=localdate)
    sold_at = models.DateTimeField(default=now)
    synced_at = models.DateTimeField(default=now)
    device_id = models.CharField(max_length=100, blank=True, null=True)
    offline_created = models.BooleanField(default=False)
    inventory_attention = models.BooleanField(default=False)
    pricing_attention = models.BooleanField(default=False)

    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))

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
        if "payments" in getattr(self, "_prefetched_objects_cache", {}):
            return sum((payment.amount for payment in self.payments.all()), Decimal("0"))
        return self.payments.aggregate(total=models.Sum("amount"))["total"] or Decimal("0")

    @property
    def amount_credited(self):
        total = Decimal("0")
        for note in self.credit_notes.all():
            total += note.amount
        return total

    @property
    def amount_refunded(self):
        if "refunds" in getattr(self, "_prefetched_objects_cache", {}):
            return sum((refund.amount for refund in self.refunds.all()), Decimal("0"))
        return self.refunds.aggregate(total=models.Sum("amount"))["total"] or Decimal("0")

    @property
    def net_total(self):
        """Invoice value after all credit notes, never below zero."""
        return max(self.total - self.amount_credited, Decimal("0"))

    @property
    def receivable(self):
        """Amount the customer still owes on this invoice."""
        return max(self.balance, Decimal("0"))

    @property
    def refund_due(self):
        """Amount the business owes the customer after returns."""
        return max(-self.balance, Decimal("0"))

    @property
    def return_status(self):
        sold_units = sum((item.quantity for item in self.items.all()), 0)
        returned_units = sum(
            (
                item.quantity
                for note in self.credit_notes.all()
                for item in note.items.all()
            ),
            0,
        )
        if returned_units <= 0:
            return self.RETURN_NONE
        if sold_units > 0 and returned_units >= sold_units:
            return self.RETURN_FULL
        return self.RETURN_PARTIAL

    @property
    def balance(self):
        """Signed compatibility field: positive is owed, negative is refundable."""
        return self.net_total - self.amount_paid + self.amount_refunded

    @property
    def payment_status(self):
        net_paid = self.amount_paid - self.amount_refunded
        if self.net_total <= 0:
            return self.PAID
        if net_paid <= 0:
            return self.PENDING
        if net_paid >= self.net_total:
            return self.PAID
        return self.PARTIAL


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, related_name="sale_items", on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.quantity} x {self.product} @ {self.unit_price}"

    @property
    def line_total(self):
        return (self.unit_price or Decimal("0")) * self.quantity


class CreditNote(models.Model):
    """A sales return: goods come back, the customer is credited (VAT-inclusive)."""
    sale = models.ForeignKey(Sale, related_name="credit_notes", on_delete=models.CASCADE)
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    reason = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(default=now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"CN-{self.pk} on {self.sale}"

    @property
    def amount(self):
        vat_factor = Decimal("1") + (self.sale.vat_rate / Decimal("100"))
        total = Decimal("0")
        for item in self.items.all():
            total += item.quantity * item.unit_price * vat_factor
        return total.quantize(Decimal("0.01"))


class CreditNoteItem(models.Model):
    credit_note = models.ForeignKey(CreditNote, related_name="items", on_delete=models.CASCADE)
    # Cascades with its sale line: a credit note only exists in the context
    # of its sale, and sale deletion handles the stock restoration itself.
    sale_item = models.ForeignKey(SaleItem, related_name="credited_items", on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)


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


class Refund(models.Model):
    """Money paid back to a customer to settle a return credit."""
    CASH = Payment.CASH
    TRANSFER = Payment.TRANSFER
    POS = Payment.POS
    METHOD_CHOICES = Payment.METHOD_CHOICES

    sale = models.ForeignKey(Sale, related_name="refunds", on_delete=models.CASCADE)
    user = models.ForeignKey(
        CustomUser, related_name="refunds_issued", on_delete=models.SET_NULL, null=True
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default=CASH)
    reference = models.CharField(max_length=100, blank=True, null=True)
    date = models.DateField(default=localdate)
    created_at = models.DateTimeField(default=now)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"Refund {self.amount} ({self.get_method_display()}) on {self.sale}"
