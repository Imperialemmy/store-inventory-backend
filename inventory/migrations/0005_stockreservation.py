import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0004_product_category"),
        ("users", "0006_customuser_session_id"),
    ]

    operations = [
        migrations.CreateModel(
            name="StockReservation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("device_id", models.CharField(max_length=100)),
                ("quantity", models.PositiveIntegerField()),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="stock_reservations", to="inventory.product")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="stock_reservations", to="users.customuser")),
            ],
            options={"ordering": ["expires_at"]},
        ),
        migrations.AddConstraint(
            model_name="stockreservation",
            constraint=models.UniqueConstraint(fields=("user", "device_id", "product"), name="unique_active_cart_product_reservation"),
        ),
    ]
