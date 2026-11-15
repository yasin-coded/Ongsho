"""Composite indexes for hot selector paths (see scripts/explain_hot_queries.py)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0003_align_charge_period_end"),
        ("dues", "0001_initial"),
        ("payments", "0002_payment_submitted_at_note"),
        ("sharing", "0003_member_leave_requested_invite_created"),
        ("audit", "0002_auditlog_plan_summary_amount"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="charge",
            index=models.Index(
                fields=["subscription", "due_date"],
                name="billing_charge_sub_due_idx",
            ),
        ),
        migrations.RunSQL(
            sql="""
            CREATE INDEX IF NOT EXISTS dues_due_member_status_idx
                ON dues_due (member_id, status);
            """,
            reverse_sql="DROP INDEX IF EXISTS dues_due_member_status_idx;",
        ),
        migrations.RunSQL(
            sql="""
            CREATE INDEX IF NOT EXISTS payments_payment_plan_review_idx
                ON payments_payment (shared_plan_id, review_status);
            """,
            reverse_sql="DROP INDEX IF EXISTS payments_payment_plan_review_idx;",
        ),
        migrations.RunSQL(
            sql="""
            CREATE INDEX IF NOT EXISTS sharing_member_plan_status_idx
                ON sharing_member (shared_plan_id, status);
            """,
            reverse_sql="DROP INDEX IF EXISTS sharing_member_plan_status_idx;",
        ),
        migrations.RunSQL(
            sql="""
            CREATE INDEX IF NOT EXISTS sharing_invite_plan_status_idx
                ON sharing_invite (shared_plan_id, status);
            """,
            reverse_sql="DROP INDEX IF EXISTS sharing_invite_plan_status_idx;",
        ),
        migrations.RunSQL(
            sql="""
            CREATE INDEX IF NOT EXISTS audit_log_plan_created_idx
                ON audit_auditlog (plan_id, created_at DESC);
            """,
            reverse_sql="DROP INDEX IF EXISTS audit_log_plan_created_idx;",
        ),
    ]