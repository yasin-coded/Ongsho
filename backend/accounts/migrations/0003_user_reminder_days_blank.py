from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_user_reminder_settings"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="reminder_days",
            field=models.CharField(blank=True, default="7,1", max_length=20),
        ),
    ]
