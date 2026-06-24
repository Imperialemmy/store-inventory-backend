from decimal import Decimal
from django.db import transaction
from rest_framework.exceptions import ValidationError
from inventory.models import Batch
from .models import Sale, SaleItem, SaleItemAllocation


def _allocate_stock(sale_item):
    """Draw `sale_item.quantity` from the variant's batches, earliest expiry
    first (FIFO for perishables), recording each draw as an allocation.

    Raises ValidationError if there isn't enough stock.
    """
    remaining = sale_item.quantity
    batches = (
        Batch.objects.select_for_update()
        .filter(variant=sale_item.variant, quantity__gt=0)
        .order_by("expiry_date", "id")
    )
    for batch in batches:
        if remaining <= 0:
            break
        take = min(batch.quantity, remaining)
        batch.quantity -= take
        batch.save()
        SaleItemAllocation.objects.create(sale_item=sale_item, batch=batch, quantity=take)
        remaining -= take

    if remaining > 0:
        raise ValidationError(
            f"Not enough stock for {sale_item.variant}: short by {remaining} unit(s)."
        )


def _restore_stock(sale):
    """Return allocated quantities to their original batches."""
    for item in sale.items.all():
        for alloc in item.allocations.all():
            batch = alloc.batch
            batch.quantity += alloc.quantity
            batch.save()


def recalculate_customer_balance(customer):
    """Set a customer's outstanding balance to the sum of unpaid amounts
    across their sales."""
    total = Decimal("0")
    for sale in customer.sales.all():
        total += sale.balance
    customer.outstanding_balance = total
    customer.save(update_fields=["outstanding_balance", "updated_at"])


@transaction.atomic
def create_sale(*, user, customer, items, discount=Decimal("0"),
                vat_rate=None, date=None, notes=None):
    """Create a sale with its line items, decrement stock FIFO, compute
    totals, and refresh the customer's balance.

    `items` is a list of dicts: {variant, quantity, unit_price?}.
    Unit price defaults to the variant's price for the customer type.
    """
    if not items:
        raise ValidationError("A sale must have at least one item.")

    sale = Sale(user=user, customer=customer, discount=discount or Decimal("0"),
                notes=notes)
    if vat_rate is not None:
        sale.vat_rate = vat_rate
    if date is not None:
        sale.date = date
    sale.save()

    for row in items:
        variant = row["variant"]
        quantity = int(row["quantity"])
        if quantity <= 0:
            raise ValidationError("Item quantity must be greater than zero.")
        unit_price = row.get("unit_price")
        if unit_price in (None, ""):
            unit_price = variant.price_for(customer.customer_type)
        sale_item = SaleItem.objects.create(
            sale=sale, variant=variant, quantity=quantity, unit_price=unit_price
        )
        _allocate_stock(sale_item)
        variant.update_availability()

    sale.recalculate()
    recalculate_customer_balance(customer)
    return sale


@transaction.atomic
def delete_sale(sale):
    """Delete a sale, returning its stock and refreshing the customer balance."""
    customer = sale.customer
    _restore_stock(sale)
    variants = {item.variant for item in sale.items.all()}
    sale.delete()
    for variant in variants:
        variant.update_availability()
    recalculate_customer_balance(customer)
