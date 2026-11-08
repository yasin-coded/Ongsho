# Generated manually to restore positive-rate check removed in 0002.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("plans", "0002_remove_exchangerate_plans_exchangerate_positive"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="exchangerate",
            constraint=models.CheckConstraint(
                condition=models.Q(usd_to_bdt__gt=0),
                name="plans_exchangerate_positive",
            ),
        ),
    ]
