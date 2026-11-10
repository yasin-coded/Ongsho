from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="email_reminders",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="user",
            name="reminder_days",
            field=models.CharField(default="7,1", max_length=20),
        ),
    ]
