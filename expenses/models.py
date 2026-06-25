from django.db import models
from django.utils.timezone import now, localdate
from users.models import CustomUser
from inventory.models import Supplier


class ExpenseCategory(models.Model):
    """A spend category, e.g. Logistics, Utilities, Rent, Purchases."""
    name = models.CharField(max_length=100, unique=True)
    monthly_budget = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "expense categories"

    def __str__(self):
        return self.name


class Expense(models.Model):
    CASH = "cash"
    TRANSFER = "transfer"
    POS = "pos"
    PETTY_CASH = "petty_cash"
    METHOD_CHOICES = (
        (CASH, "Cash"),
        (TRANSFER, "Bank Transfer"),
        (POS, "POS"),
        (PETTY_CASH, "Petty Cash"),
    )

    user = models.ForeignKey(CustomUser, related_name="expenses", on_delete=models.SET_NULL, null=True)
    category = models.ForeignKey(ExpenseCategory, related_name="expenses", on_delete=models.PROTECT)
    supplier = models.ForeignKey(
        Supplier, related_name="expenses", on_delete=models.SET_NULL, null=True, blank=True
    )
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=METHOD_CHOICES, default=CASH)
    reference = models.CharField(max_length=100, blank=True, null=True)
    receipt = models.FileField(upload_to="receipts/", blank=True, null=True)
    date = models.DateField(default=localdate)
    created_at = models.DateTimeField(default=now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.description} — {self.amount}"
