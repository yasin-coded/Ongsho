from django.db import migrations


def seed_cursor(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    ServiceName = apps.get_model("catalog", "ServiceName")
    category = Category.objects.filter(name="AI tools", is_preset=True, user=None).first()
    if category is None:
        return
    ServiceName.objects.get_or_create(
        name="Cursor",
        category=category,
        is_preset=True,
        user=None,
        defaults={"is_preset": True},
    )


def unseed_cursor(apps, schema_editor):
    ServiceName = apps.get_model("catalog", "ServiceName")
    ServiceName.objects.filter(name="Cursor", is_preset=True, user=None).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0002_seed_presets"),
    ]

    operations = [
        migrations.RunPython(seed_cursor, unseed_cursor),
    ]
