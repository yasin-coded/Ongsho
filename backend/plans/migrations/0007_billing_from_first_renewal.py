from datetime import timedelta

from django.db import migrations


def _nth_month_due(first, anchor_day, months):
    from calendar import monthrange

    y = first.year
    m = first.month + months
    while m > 12:
        y += 1
        m -= 12
    last = monthrange(y, m)[1]
    from datetime import date

    return date(y, m, min(anchor_day, last))


def _first_renewal(sub):
    if sub.trial_end_date:
        return sub.trial_end_date
    start = sub.start_date
    unit = sub.cycle_unit
    count = sub.cycle_count or 1
    if unit == "month":
        return _nth_month_due(start, sub.anchor_day, count)
    if unit == "year":
        return _nth_month_due(start, sub.anchor_day, count * 12)
    if unit == "week":
        return start + timedelta(days=7 * count)
    if unit == "day":
        return start + timedelta(days=count)
    return start


def align_billing_from_first_renewal(apps, schema_editor):
    Subscription = apps.get_model("plans", "Subscription")
    for sub in Subscription.objects.iterator():
        target = _first_renewal(sub)
        if sub.billing_from != target:
            sub.billing_from = target
            sub.save(update_fields=["billing_from"])


class Migration(migrations.Migration):
    dependencies = [
        ("plans", "0006_billing_from_plan_start"),
    ]

    operations = [
        migrations.RunPython(align_billing_from_first_renewal, migrations.RunPython.noop),
    ]