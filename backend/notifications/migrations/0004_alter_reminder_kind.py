# Generated to align Reminder.kind choices with ReminderKind (due_soon).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0003_reminder_subscription_target"),
    ]

    operations = [
        migrations.AlterField(
            model_name="reminder",
            name="kind",
            field=models.CharField(
                choices=[
                    ("renewal", "Renewal"),
                    ("trial_end", "Trial end"),
                    ("expiry", "Expiry"),
                    ("due_soon", "Due soon"),
                ],
                max_length=16,
            ),
        ),
    ]