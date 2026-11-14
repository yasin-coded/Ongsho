from datetime import date

from django.db import migrations

from core.schedule import Schedule, first_renewal_date


def align_billing_from(apps, schema_editor):
    Subscription = apps.get_model("plans", "Subscription")
    for sub in Subscription.objects.filter(trial_end_date__isnull=True):
        if sub.billing_from != sub.start_date:
            continue
        schedule = Schedule(
            start_date=sub.start_date,
            trial_end_date=None,
            anchor_day=sub.anchor_day,
            cycle_unit=sub.cycle_unit,
            cycle_count=sub.cycle_count,
            renewal_type=sub.renewal_type,
            end_date=sub.end_date,
            paused_on=sub.paused_on,
            cancelled_on=sub.cancelled_on,
            status=sub.status,
        )
        target = first_renewal_date(schedule)
        if target != sub.billing_from:
            sub.billing_from = target
            sub.save(update_fields=["billing_from"])


class Migration(migrations.Migration):
    dependencies = [
        ("plans", "0004_subscription_billing_and_status_dates"),
    ]

    operations = [
        migrations.RunPython(align_billing_from, migrations.RunPython.noop),
    ]