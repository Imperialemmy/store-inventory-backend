from django.db.models import Sum
from .models import Batch, WareVariant

def receive_stock(ware_variant, quantity, expiry_date, lot_number):
    """
    Receives new stock, updates batch records, and recalculates total stock.
    """
    Batch.objects.create(
        variant=ware_variant,
        quantity=quantity,
        expiry_date=expiry_date,
        lot_number=lot_number,
    )

    # Recalculate stock from all batches (including expired ones)
    ware_variant.stock = Batch.objects.filter(variant=ware_variant).aggregate(
        total=Sum("quantity")
    )["total"] or 0
    ware_variant.save()

def adjust_stock(batch, new_quantity):
    """
    Adjusts stock for a batch and updates the total variant stock.
    """
    batch.quantity = new_quantity
    batch.save()

    ware_variant = batch.variant
    ware_variant.stock = Batch.objects.filter(variant=ware_variant).aggregate(
        total=Sum("quantity")
    )["total"] or 0
    ware_variant.save()
