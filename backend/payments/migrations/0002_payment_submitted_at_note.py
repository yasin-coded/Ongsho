from django.db import migrations, models
from django.utils import timezone


def backfill_submitted_at(apps, schema_editor):
    Payment = apps.get_model("payments", "Payment")
    now = timezone.now()
    for payment in Payment.objects.filter(submitted_at__isnull=True):
        payment.submitted_at = payment.reviewed_at or now
        payment.save(update_fields=["submitted_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="note",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="payment",
            name="submitted_at",
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.RunPython(backfill_submitted_at, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="payment",
            name="submitted_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
    ]
