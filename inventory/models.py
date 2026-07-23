from django.db import models
from django.utils.timezone import now
from users.models import CustomUser


class Product(models.Model):
    """A single sellable product: a name, an optional image, a price and a
    running stock count. Sales draw the count down; deletions and returns
    put it back."""
    name = models.CharField(max_length=150, unique=True)
    category = models.CharField(max_length=50, blank=True, default="")
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Stock may temporarily be negative when two devices sell the final units
    # while offline. The movement ledger preserves what really happened and
    # the admin UI can resolve the resulting attention item.
    stock = models.IntegerField(default=0)
    reorder_level = models.PositiveIntegerField(default=5)
    cost_price = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )
    created_at = models.DateTimeField(default=now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class AuditLog(models.Model):
    """Append-only record of who changed what and when."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    ACTION_CHOICES = (
        (CREATE, "Create"),
        (UPDATE, "Update"),
        (DELETE, "Delete"),
    )

    user = models.ForeignKey(
        CustomUser, related_name="audit_logs", on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=64, blank=True, null=True)
    object_repr = models.CharField(max_length=255, blank=True, null=True)
    changes = models.JSONField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.action} {self.model_name}#{self.object_id}"


class InventoryMovement(models.Model):
    OPENING = "opening"
    RESTOCK = "restock"
    SALE = "sale"
    RETURN = "return"
    DAMAGE = "damage"
    CORRECTION = "correction"
    REVERSAL = "reversal"
    REASON_CHOICES = (
        (OPENING, "Opening stock"),
        (RESTOCK, "Restock"),
        (SALE, "Sale"),
        (RETURN, "Return"),
        (DAMAGE, "Damage or expiry"),
        (CORRECTION, "Correction"),
        (REVERSAL, "Sale reversal"),
    )

    product = models.ForeignKey(
        Product, related_name="inventory_movements", on_delete=models.SET_NULL,
        blank=True, null=True,
    )
    sale = models.ForeignKey(
        "sales.Sale", related_name="inventory_movements",
        on_delete=models.SET_NULL, blank=True, null=True,
    )
    user = models.ForeignKey(
        CustomUser, related_name="inventory_movements",
        on_delete=models.SET_NULL, blank=True, null=True,
    )
    quantity = models.IntegerField()
    stock_after = models.IntegerField()
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    client_reference = models.CharField(
        max_length=160, unique=True, blank=True, null=True
    )
    device_id = models.CharField(max_length=100, blank=True, null=True)
    event_at = models.DateTimeField(default=now)
    synced_at = models.DateTimeField(blank=True, null=True)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-event_at", "-id"]

    def __str__(self):
        return f"{self.get_reason_display()}: {self.quantity:+d} {self.product or 'deleted product'}"
