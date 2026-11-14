from django.db import migrations


def align_billing_from_start(apps, schema_editor):
    Subscription = apps.get_model("plans", "Subscription")
    for sub in Subscription.objects.iterator():
        target = sub.trial_end_date if sub.trial_end_date else sub.start_date
        if sub.billing_from != target:
            sub.billing_from = target
            sub.save(update_fields=["billing_from"])


class Migration(migrations.Migration):
    dependencies = [
        ("plans", "0005_align_billing_from_first_renewal"),
    ]

    operations = [
        migrations.RunPython(align_billing_from_start, migrations.RunPython.noop),
    ]