from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0001_initial"),
        ("sales", "0003_sale_offline_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="cost_price",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=10, null=True
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="reorder_level",
            field=models.PositiveIntegerField(default=5),
        ),
        migrations.AlterField(
            model_name="product",
            name="stock",
            field=models.IntegerField(default=0),
        ),
        migrations.CreateModel(
            name="InventoryMovement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.IntegerField()),
                ("stock_after", models.IntegerField()),
                ("reason", models.CharField(choices=[("opening", "Opening stock"), ("restock", "Restock"), ("sale", "Sale"), ("return", "Return"), ("damage", "Damage or expiry"), ("correction", "Correction"), ("reversal", "Sale reversal")], max_length=20)),
                ("client_reference", models.CharField(blank=True, max_length=160, null=True, unique=True)),
                ("device_id", models.CharField(blank=True, max_length=100, null=True)),
                ("event_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("synced_at", models.DateTimeField(blank=True, null=True)),
                ("note", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("product", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="inventory_movements", to="inventory.product")),
                ("sale", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="inventory_movements", to="sales.sale")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="inventory_movements", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-event_at", "-id"]},
        ),
    ]
