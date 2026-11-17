"""Hot query indexes — charge_list_by_subscription (scripts/explain_hot_queries.py)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0003_align_charge_period_end"),
    ]

    operations = [
        # charge_list_by_subscription: subscription_id filter + ORDER BY due_date
        migrations.AddIndex(
            model_name="charge",
            index=models.Index(
                fields=["subscription", "due_date"],
                name="billing_charge_sub_due_idx",
            ),
        ),
    ]