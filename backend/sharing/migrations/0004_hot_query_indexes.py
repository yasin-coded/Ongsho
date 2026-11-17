"""Hot query indexes — member_active_by_plan and invite list by plan (scripts/explain_hot_queries.py)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sharing", "0003_member_leave_requested_invite_created"),
    ]

    operations = [
        # member_active_by_plan: shared_plan_id + status filter
        migrations.AddIndex(
            model_name="member",
            index=models.Index(
                fields=["shared_plan", "status"],
                name="sharing_member_plan_status_idx",
            ),
        ),
        # pending_invites_by_plan: shared_plan_id + status filter
        migrations.AddIndex(
            model_name="invite",
            index=models.Index(
                fields=["shared_plan", "status"],
                name="sharing_invite_plan_status_idx",
            ),
        ),
    ]