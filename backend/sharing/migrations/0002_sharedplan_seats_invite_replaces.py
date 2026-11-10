import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sharing", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="sharedplan",
            name="seats",
            field=models.PositiveSmallIntegerField(default=2),
        ),
        migrations.AddField(
            model_name="invite",
            name="replaces_member",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="replacement_invites",
                to="sharing.member",
            ),
        ),
        migrations.AddConstraint(
            model_name="sharedplan",
            constraint=models.CheckConstraint(
                condition=models.Q(("seats__gte", 1), ("seats__lte", 20)),
                name="sharing_sharedplan_seats_range",
            ),
        ),
    ]
