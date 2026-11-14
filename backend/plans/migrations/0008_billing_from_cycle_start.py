from django.db import migrations


def _billing_floor(sub):
    return sub.trial_end_date if sub.trial_end_date else sub.start_date


def align_billing_from_cycle_start(apps, schema_editor):
    Subscription = apps.get_model("plans", "Subscription")
    for sub in Subscription.objects.iterator():
        target = _billing_floor(sub)
        if sub.billing_from != target:
            sub.billing_from = target
            sub.save(update_fields=["billing_from"])


def backfill_shared_dues(apps, schema_editor):
    from billing.models import Charge
    from dues.services import create_dues_for_charge
    from sharing.models import SharedPlan

    sub_ids = list(SharedPlan.objects.values_list("subscription_id", flat=True))
    if not sub_ids:
        return
    for charge in Charge.objects.filter(subscription_id__in=sub_ids).iterator():
        create_dues_for_charge(charge)


class Migration(migrations.Migration):
    dependencies = [
        ("plans", "0007_billing_from_first_renewal"),
        ("billing", "0002_remove_pre_billing_charges"),
        ("sharing", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(align_billing_from_cycle_start, migrations.RunPython.noop),
        migrations.RunPython(backfill_shared_dues, migrations.RunPython.noop),
    ]