from .models import Batch, WareVariant


def receive_stock(ware_variant, quantity, expiry_date, lot_number,
                  warehouse=None, supplier=None, manufacturing_date=None):
    """
    Record a stock delivery as a new batch.

    Stock totals are derived from batch quantities (see
    ``WareVariant.get_stock``), so creating the batch is all that is required;
    ``Batch.save`` refreshes the variant's availability flag.
    """
    return Batch.objects.create(
        variant=ware_variant,
        warehouse=warehouse,
        supplier=supplier,
        quantity=quantity,
        expiry_date=expiry_date,
        manufacturing_date=manufacturing_date,
        lot_number=lot_number,
    )


def adjust_stock(batch, new_quantity):
    """
    Adjust the quantity held in a single batch (damages, losses, corrections).

    ``Batch.save`` recalculates the parent variant's availability.
    """
    batch.quantity = new_quantity
    batch.save()
    return batch


def low_stock_variants(warehouse=None):
    """
    Return variants whose total stock is at or below their reorder point.

    Reorder logic is per-variant, so this evaluates each variant in Python;
    pass a ``warehouse`` to scope the stock count to one location.
    """
    variants = WareVariant.objects.select_related('ware').all()
    return [v for v in variants if v.get_stock(warehouse) <= v.reorder_point]
