import uuid

from django.db import migrations, models
import django.utils.timezone


def populate_client_sale_ids(apps, schema_editor):
    Sale = apps.get_model("sales", "Sale")
    for sale in Sale.objects.filter(client_sale_id__isnull=True).iterator():
        sale.client_sale_id = uuid.uuid4()
        sale.save(update_fields=["client_sale_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0002_alter_creditnoteitem_sale_item"),
    ]

    operations = [
        migrations.AddField(
            model_name="sale",
            name="client_sale_id",
            field=models.UUIDField(null=True),
        ),
        migrations.AddField(
            model_name="sale",
            name="device_id",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="sale",
            name="inventory_attention",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="sale",
            name="offline_created",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="sale",
            name="pricing_attention",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="sale",
            name="sold_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name="sale",
            name="synced_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.RunPython(populate_client_sale_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="sale",
            name="client_sale_id",
            field=models.UUIDField(
                db_index=True, default=uuid.uuid4, editable=False, unique=True
            ),
        ),
    ]
