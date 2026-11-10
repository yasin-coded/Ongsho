import django.utils.timezone
from django.db import migrations, models
from django.utils import timezone as dj_tz


def backfill_billing_from(apps, schema_editor):
    Subscription = apps.get_model("plans", "Subscription")
    for sub in Subscription.objects.all().iterator():
        created = sub.created_at
        if dj_tz.is_naive(created):
            created = dj_tz.make_aware(created, dj_tz.get_current_timezone())
        sub.billing_from = dj_tz.localtime(created).date()
        sub.save(update_fields=["billing_from"])


class Migration(migrations.Migration):

    dependencies = [
        ("plans", "0003_exchangerate_plans_exchangerate_positive"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscription",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="subscription",
            name="billing_from",
            field=models.DateField(null=True),
        ),
        migrations.AddField(
            model_name="subscription",
            name="paused_on",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="subscription",
            name="cancelled_on",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_billing_from, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="subscription",
            name="billing_from",
            field=models.DateField(),
        ),
    ]
