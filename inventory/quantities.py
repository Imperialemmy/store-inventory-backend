"""Exact quantity parsing shared by inventory and sales workflows."""

from decimal import Decimal, InvalidOperation


QUANTITY_STEP = Decimal("0.25")
STORAGE_QUANTUM = Decimal("0.0001")


def parse_stored_quantity(value, *, allow_negative=False):
    """Parse exact stored stock, including a legacy non-quarter remainder."""
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Enter a valid quantity.") from exc
    if not quantity.is_finite():
        raise ValueError("Enter a valid quantity.")
    if quantity < 0 and not allow_negative:
        raise ValueError("Quantity cannot be negative.")
    return quantity.quantize(STORAGE_QUANTUM)


def parse_quarter_quantity(value, *, allow_zero=False, allow_negative=False):
    """Return an exact quantity limited to full, half, or quarter units."""
    quantity = parse_stored_quantity(value, allow_negative=allow_negative)
    if quantity == 0 and not allow_zero:
        raise ValueError("Quantity must be greater than zero.")
    if quantity < 0 and not allow_negative:
        raise ValueError("Quantity cannot be negative.")
    if quantity % QUANTITY_STEP != 0:
        raise ValueError(
            "Quantity must be in quarter-unit steps "
            "(0.25, 0.50, 0.75, or a whole number)."
        )
    return quantity
