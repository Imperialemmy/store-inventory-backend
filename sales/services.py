from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import ValidationError
from inventory.models import Product
from .models import Sale, SaleItem, CreditNote, CreditNoteItem


def recalculate_customer_balance(customer):
    """Set a customer's outstanding balance to the sum of unpaid amounts."""
    total = Decimal("0")
    for sale in customer.sales.all():
        total += sale.balance
    customer.outstanding_balance = total
    customer.save(update_fields=["outstanding_balance", "updated_at"])


def credited_quantity(sale_item):
    """Units of this line already returned on previous credit notes."""
    return sale_item.credited_items.aggregate(t=Sum("quantity"))["t"] or 0


@transaction.atomic
def create_sale(*, user, customer, items, discount=Decimal("0"),
                vat_rate=None, date=None, notes=None):
    """Create a sale with its line items, decrement product stock, compute
    totals, and refresh the customer's balance.

    `items` is a list of {product, quantity, unit_price?}. Unit price
    defaults to the product's price.
    """
    if not items:
        raise ValidationError("A sale must have at least one item.")

    sale = Sale(user=user, customer=customer, discount=discount or Decimal("0"), notes=notes)
    if vat_rate is not None:
        sale.vat_rate = vat_rate
    if date is not None:
        sale.date = date
    sale.save()

    for row in items:
        product = row["product"]
        quantity = int(row["quantity"])
        if quantity <= 0:
            raise ValidationError("Item quantity must be greater than zero.")

        # Lock the product row and check stock.
        product = Product.objects.select_for_update().get(pk=product.pk)
        if quantity > product.stock:
            raise ValidationError(
                f"Not enough stock for {product.name}: short by {quantity - product.stock} unit(s)."
            )

        unit_price = row.get("unit_price")
        if unit_price in (None, ""):
            unit_price = product.price

        SaleItem.objects.create(sale=sale, product=product, quantity=quantity, unit_price=unit_price)
        product.stock -= quantity
        product.save(update_fields=["stock", "updated_at"])

    sale.recalculate()
    recalculate_customer_balance(customer)
    return sale


@transaction.atomic
def delete_sale(sale):
    """Delete a sale, returning its stock and refreshing the customer balance.

    Units already returned on credit notes were restocked when the return was
    recorded, so only the un-returned remainder goes back now.
    """
    customer = sale.customer
    for item in sale.items.select_related("product"):
        remaining = item.quantity - credited_quantity(item)
        if remaining > 0:
            product = Product.objects.select_for_update().get(pk=item.product_id)
            product.stock += remaining
            product.save(update_fields=["stock", "updated_at"])
    sale.delete()
    recalculate_customer_balance(customer)


@transaction.atomic
def create_credit_note(*, sale, items, user=None, reason=None):
    """Record a sales return: restock the products and credit the customer."""
    if not items:
        raise ValidationError("A credit note must have at least one item.")

    note = CreditNote.objects.create(sale=sale, user=user, reason=reason)

    for row in items:
        sale_item = row["sale_item"]
        quantity = int(row["quantity"])
        if sale_item.sale_id != sale.id:
            raise ValidationError("Item does not belong to this sale.")
        returnable = sale_item.quantity - credited_quantity(sale_item)
        if quantity <= 0 or quantity > returnable:
            raise ValidationError(
                f"Can return at most {returnable} unit(s) of {sale_item.product.name}."
            )

        CreditNoteItem.objects.create(
            credit_note=note, sale_item=sale_item,
            quantity=quantity, unit_price=sale_item.unit_price,
        )
        product = Product.objects.select_for_update().get(pk=sale_item.product_id)
        product.stock += quantity
        product.save(update_fields=["stock", "updated_at"])

    recalculate_customer_balance(sale.customer)
    return note
