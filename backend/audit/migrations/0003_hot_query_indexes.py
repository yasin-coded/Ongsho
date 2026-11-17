"""Hot query indexes — audit_by_plan (scripts/explain_hot_queries.py)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0002_auditlog_plan_summary_amount"),
    ]

    operations = [
        # audit_by_plan: plan_id filter + ORDER BY created_at DESC
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(
                fields=["plan_id", "-created_at"],
                name="audit_log_plan_created_idx",
            ),
        ),
    ]