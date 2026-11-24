# Generated manually for payment receipt outbox type

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_outbound_email_integrity"),
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
                ],
                max_length=32,
            ),
        ),
    ]