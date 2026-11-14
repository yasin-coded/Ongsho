from django.db import migrations


def align_period_end_to_due(apps, schema_editor):
    Charge = apps.get_model("billing", "Charge")
    for charge in Charge.objects.iterator():
        if charge.period_end != charge.due_date:
            charge.period_end = charge.due_date
            charge.save(update_fields=["period_end"])


def backfill_charges_and_dues(apps, schema_editor):
    from billing import services as billing_services
    from core.dates import today_dhaka
    from dues.services import create_dues_for_charge
    from billing.models import Charge
    from plans.models import Subscription

    today = today_dhaka()
    for sub in Subscription.objects.filter(archived_on__isnull=True).iterator():
        billing_services.generate_missing_charges(sub, today)
    for charge in Charge.objects.filter(subscription__shared_plan__isnull=False).iterator():
        create_dues_for_charge(charge)


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0002_remove_pre_billing_charges"),
        ("plans", "0008_billing_from_cycle_start"),
        ("sharing", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(align_period_end_to_due, migrations.RunPython.noop),
        migrations.RunPython(backfill_charges_and_dues, migrations.RunPython.noop),
    ]