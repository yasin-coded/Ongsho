"""Hot query indexes — payment_pending_by_plan (scripts/explain_hot_queries.py)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0002_payment_submitted_at_note"),
    ]

    operations = [
        # payment_pending_by_plan: shared_plan_id + review_status filter
        migrations.AddIndex(
            model_name="payment",
            index=models.Index(
                fields=["shared_plan", "review_status"],
                name="payments_plan_review_idx",
            ),
        ),
    ]