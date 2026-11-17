"""Hot query indexes — due_by_member_status (scripts/explain_hot_queries.py)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dues", "0001_initial"),
    ]

    operations = [
        # due_by_member_status: member_id + status filter
        migrations.AddIndex(
            model_name="due",
            index=models.Index(
                fields=["member", "status"],
                name="dues_due_member_status_idx",
            ),
        ),
    ]