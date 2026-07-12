"""Transactional inventory helpers backed by an append-only movement ledger."""

import uuid

from django.db import transaction
from django.utils.timezone import now
from rest_framework.exceptions import ValidationError

from .models import InventoryMovement, Product


@transaction.atomic
def adjust_inventory(*, product, quantity, reason, user=None, note="", event_at=None):
    quantity = int(quantity)
    if quantity == 0:
        raise ValidationError("Inventory adjustment cannot be zero.")
    allowed = {
        InventoryMovement.OPENING,
        InventoryMovement.RESTOCK,
        InventoryMovement.DAMAGE,
        InventoryMovement.CORRECTION,
    }
    if reason not in allowed:
        raise ValidationError("Choose a valid inventory adjustment reason.")
    if reason == InventoryMovement.RESTOCK and quantity < 0:
        raise ValidationError("A restock quantity must be positive.")
    if reason == InventoryMovement.DAMAGE and quantity > 0:
        raise ValidationError("Damage or expiry quantity must be negative.")

    locked = Product.objects.select_for_update().get(pk=product.pk)
    locked.stock += quantity
    locked.save(update_fields=["stock", "updated_at"])
    return InventoryMovement.objects.create(
        product=locked,
        user=user,
        quantity=quantity,
        stock_after=locked.stock,
        reason=reason,
        client_reference=f"adjust:{uuid.uuid4()}",
        event_at=event_at or now(),
        synced_at=now(),
        note=note,
    )
