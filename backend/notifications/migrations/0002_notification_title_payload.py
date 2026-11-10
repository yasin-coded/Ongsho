from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="title",
            field=models.CharField(default="", max_length=120),
        ),
        migrations.AddField(
            model_name="notification",
            name="payload",
            field=models.JSONField(default=dict),
        ),
    ]
