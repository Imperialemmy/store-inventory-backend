from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("sales", "0005_refund"),
    ]

    operations = [
        migrations.AddField(
            model_name="sale", name="inventory_resolution",
            field=models.CharField(blank=True, choices=[("stock_corrected", "Stock corrected"), ("backorder", "Accepted as backorder"), ("accepted_negative", "Intentional negative stock")], default="", max_length=30),
        ),
        migrations.AddField(
            model_name="sale", name="inventory_resolution_note",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="sale", name="inventory_resolved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="sale", name="inventory_resolved_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="resolved_inventory_conflicts", to=settings.AUTH_USER_MODEL),
        ),
    ]
