# Payment rejection notification outbox type

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_email_change_completion_types"),
    ]

    operations = [
        migrations.AlterField(
            model_name="outboundemail",
            name="email_type",
            field=models.CharField(
                choices=[
                    ("account_verify", "Account verification"),
                    ("verify_resend", "Resend verification"),
                    ("password_reset", "Password reset"),
                    ("email_change", "Email change verification"),
                    ("plan_invite", "Plan invitation"),
                    ("reminder", "Due or renewal reminder"),
                    ("payment_receipt", "Payment receipt"),
                    ("payment_rejected", "Payment rejected"),
                    ("password_changed", "Password changed"),
                    ("password_reset_completed", "Password reset completed"),
                    ("email_changed_new", "Email changed (new address)"),
                    ("email_changed_previous", "Email changed (previous address)"),
                ],
                max_length=32,
            ),
        ),
    ]