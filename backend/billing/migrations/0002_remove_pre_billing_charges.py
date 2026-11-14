from django.db import migrations


def remove_pre_billing_charges(apps, schema_editor):
    Charge = apps.get_model("billing", "Charge")
    PaymentAllocation = apps.get_model("payments", "PaymentAllocation")

    for charge in Charge.objects.select_related("subscription").iterator():
        sub = charge.subscription
        if charge.due_date >= sub.billing_from:
            continue
        if PaymentAllocation.objects.filter(due__charge_id=charge.pk).exists():
            continue
        charge.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0001_initial"),
        ("payments", "0001_initial"),
        ("plans", "0005_align_billing_from_first_renewal"),
    ]

    operations = [
        migrations.RunPython(remove_pre_billing_charges, migrations.RunPython.noop),
    ]