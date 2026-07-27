from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("customers", "0002_remove_customer_credit_limit_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="legacy_id",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
    ]
