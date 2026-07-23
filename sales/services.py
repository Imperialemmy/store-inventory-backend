from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.utils.timezone import localtime, now
from django.conf import settings
from rest_framework.exceptions import ValidationError
from inventory.models import Product, InventoryMovement
from .models import Sale, SaleItem, Payment, Refund, CreditNote, CreditNoteItem


def credited_quantity(sale_item):
    """Units of this line already returned on previous credit notes."""
    return sale_item.credited_items.aggregate(t=Sum("quantity"))["t"] or 0


@transaction.atomic
def create_sale(*, user, customer, items, discount=Decimal("0"),
                vat_rate=None, date=None, notes=None, client_sale_id=None,
                sold_at=None, device_id=None, offline_created=False,
                payment=None):
    """Create a sale with its line items, decrement product stock, compute
    totals, and refresh the customer's balance.

    `items` is a list of {product, quantity, unit_price?}. Unit price
    defaults to the product's price.
    """
    if not items:
        raise ValidationError("A sale must have at least one item.")

    if client_sale_id:
        existing = Sale.objects.filter(client_sale_id=client_sale_id).first()
        if existing:
            return existing, False

    sale = Sale(
        user=user,
        customer=customer,
        discount=discount or Decimal("0"),
        notes=notes,
        sold_at=sold_at or now(),
        synced_at=now(),
        device_id=device_id,
        offline_created=offline_created,
    )
    if client_sale_id:
        sale.client_sale_id = client_sale_id
    if vat_rate is not None and offline_created:
        sale.vat_rate = vat_rate
    elif not offline_created:
        sale.vat_rate = settings.DEFAULT_VAT_RATE
    sale.date = date if date is not None else localtime(sale.sold_at).date()
    sale.save()

    seen_products = set()
    for row in items:
        product = row["product"]
        if product.pk in seen_products:
            raise ValidationError(f"{product.name} appears more than once in this sale.")
        seen_products.add(product.pk)
        quantity = int(row["quantity"])
        if quantity <= 0:
            raise ValidationError("Item quantity must be greater than zero.")

        # Lock the product row and check stock.
        product = Product.objects.select_for_update().get(pk=product.pk)
        if quantity > product.stock and not offline_created:
            raise ValidationError(
                f"Not enough stock for {product.name}: short by {quantity - product.stock} unit(s)."
            )

        unit_price = row.get("unit_price")
        if unit_price in (None, ""):
            unit_price = product.price
        else:
            unit_price = Decimal(str(unit_price))
            if unit_price != product.price:
                if offline_created:
                    sale.pricing_attention = True
                elif getattr(user, "role", None) != "admin":
                    raise ValidationError(
                        f"The price for {product.name} changed. Refresh products and try again."
                    )

        SaleItem.objects.create(sale=sale, product=product, quantity=quantity, unit_price=unit_price)
        product.stock -= quantity
        product.save(update_fields=["stock", "updated_at"])
        InventoryMovement.objects.create(
            product=product,
            sale=sale,
            user=user,
            quantity=-quantity,
            stock_after=product.stock,
            reason=InventoryMovement.SALE,
            client_reference=f"sale:{sale.client_sale_id}:{product.pk}",
            device_id=device_id,
            event_at=sale.sold_at,
            synced_at=sale.synced_at,
        )
        if product.stock < 0:
            sale.inventory_attention = True

    sale.recalculate()
    if sale.inventory_attention or sale.pricing_attention:
        sale.save(update_fields=[
            "inventory_attention", "pricing_attention", "updated_at"
        ])

    if payment:
        amount = Decimal(str(payment.get("amount", "0")))
        method = payment.get("method", Payment.CASH)
        valid_methods = {choice[0] for choice in Payment.METHOD_CHOICES}
        if method not in valid_methods:
            raise ValidationError("Choose a valid payment method.")
        if amount <= 0:
            raise ValidationError("Payment amount must be greater than zero.")
        if amount > sale.total and amount <= sale.total + Decimal("0.01"):
            amount = sale.total
        if amount > sale.total:
            raise ValidationError("Payment cannot be greater than the sale total.")
        Payment.objects.create(
            sale=sale,
            amount=amount,
            method=method,
            reference=payment.get("reference") or None,
            date=sale.date,
        )

    # A walk-in has no name to collect a debt from, so the sale must be
    # settled in full at the till.
    if customer.name == "Walk-in Customer" and sale.balance > 0:
        raise ValidationError(
            "Walk-in sales must be paid in full. Pick a named customer to sell on credit."
        )
    return sale, True


@transaction.atomic
def delete_sale(sale):
    """Delete a sale, returning its stock and refreshing the customer balance.

    Units already returned on credit notes were restocked when the return was
    recorded, so only the un-returned remainder goes back now.
    """
    for item in sale.items.select_related("product"):
        remaining = item.quantity - credited_quantity(item)
        if remaining > 0:
            product = Product.objects.select_for_update().get(pk=item.product_id)
            product.stock += remaining
            product.save(update_fields=["stock", "updated_at"])
            InventoryMovement.objects.create(
                product=product,
                user=getattr(sale, "_acting_user", None),
                quantity=remaining,
                stock_after=product.stock,
                reason=InventoryMovement.REVERSAL,
                client_reference=f"delete:{sale.client_sale_id}:{product.pk}",
                device_id=sale.device_id,
                note=f"Reversal of {sale.invoice_number}",
            )
    sale.delete()


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
        InventoryMovement.objects.create(
            product=product,
            sale=sale,
            user=user,
            quantity=quantity,
            stock_after=product.stock,
            reason=InventoryMovement.RETURN,
            client_reference=f"return:{note.pk}:{sale_item.pk}",
            event_at=note.created_at,
            synced_at=now(),
        )

    return note


@transaction.atomic
def create_refund(*, sale, amount, method, user=None, reference=None):
    """Record money paid back against a sale's current refund liability."""
    locked_sale = Sale.objects.select_for_update().get(pk=sale.pk)
    amount = Decimal(str(amount))
    if amount <= 0:
        raise ValidationError("Refund amount must be greater than zero.")
    if method not in {choice[0] for choice in Refund.METHOD_CHOICES}:
        raise ValidationError("Choose a valid refund method.")
    if amount > locked_sale.refund_due:
        raise ValidationError(
            f"Refund cannot exceed the remaining refund due of {locked_sale.refund_due}."
        )
    return Refund.objects.create(
        sale=locked_sale,
        user=user,
        amount=amount,
        method=method,
        reference=reference or None,
    )
