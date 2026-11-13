from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def clear_reminders(apps, schema_editor):
    Reminder = apps.get_model("notifications", "Reminder")
    Reminder.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0001_initial"),
        ("notifications", "0002_notification_title_payload"),
        ("plans", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="reminder",
            name="notifications_reminder_unique",
        ),
        migrations.RunPython(clear_reminders, migrations.RunPython.noop),
        migrations.AddField(
            model_name="reminder",
            name="subscription",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="reminders",
                to="plans.subscription",
            ),
        ),
        migrations.AddField(
            model_name="reminder",
            name="target_date",
            field=models.DateField(null=True),
        ),
        migrations.AlterField(
            model_name="reminder",
            name="charge",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="reminders",
                to="billing.charge",
            ),
        ),
        migrations.RemoveField(
            model_name="reminder",
            name="send_on",
        ),
        migrations.AlterField(
            model_name="reminder",
            name="subscription",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="reminders",
                to="plans.subscription",
            ),
        ),
        migrations.AlterField(
            model_name="reminder",
            name="target_date",
            field=models.DateField(),
        ),
        migrations.AddConstraint(
            model_name="reminder",
            constraint=models.UniqueConstraint(
                fields=("kind", "subscription", "target_date", "days_before", "user"),
                name="notifications_reminder_unique",
            ),
        ),
    ]
