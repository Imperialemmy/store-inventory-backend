from django.db import migrations
from django.utils.timezone import now


def backfill_opening_movements(apps, schema_editor):
    Product = apps.get_model("inventory", "Product")
    InventoryMovement = apps.get_model("inventory", "InventoryMovement")
    for product in Product.objects.all().iterator():
        if product.stock == 0 or InventoryMovement.objects.filter(product=product).exists():
            continue
        InventoryMovement.objects.create(
            product=product,
            quantity=product.stock,
            stock_after=product.stock,
            reason="opening",
            client_reference=f"legacy-opening:{product.pk}",
            event_at=product.created_at,
            synced_at=now(),
            note="Opening balance captured during ledger migration",
        )


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0002_product_tracking_and_movements"),
    ]

    operations = [
        migrations.RunPython(backfill_opening_movements, migrations.RunPython.noop),
    ]
