from django.db import migrations

PRESET_CATEGORIES = [
    "Streaming",
    "Music",
    "AI tools",
    "Software",
    "Hosting",
    "Internet",
    "Utilities",
    "Other",
]

PRESET_SERVICES = {
    "Streaming": [
        "Netflix",
        "YouTube Premium",
        "Disney+ Hotstar",
        "Amazon Prime Video",
        "Hoichoi",
        "Chorki",
        "Bongo",
    ],
    "Music": ["Spotify", "Apple Music", "YouTube Music"],
    "AI tools": ["ChatGPT", "Claude", "Gemini", "Midjourney", "GitHub Copilot"],
    "Software": [
        "Canva",
        "Microsoft 365",
        "Adobe Creative Cloud",
        "Notion",
        "Figma",
        "Google One",
        "iCloud+",
    ],
    "Hosting": [
        "Vercel",
        "Render",
        "DigitalOcean",
        "Namecheap (domains)",
        "GoDaddy (domains)",
        "Cloudflare",
    ],
    "Internet": ["Home broadband", "Mobile data pack"],
    "Utilities": ["Electricity", "Gas", "Water"],
}


def seed_presets(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    ServiceName = apps.get_model("catalog", "ServiceName")
    for name in PRESET_CATEGORIES:
        Category.objects.get_or_create(name=name, is_preset=True, user=None, defaults={"is_preset": True})
    for category_name, services in PRESET_SERVICES.items():
        category = Category.objects.get(name=category_name, is_preset=True, user=None)
        for service in services:
            ServiceName.objects.get_or_create(
                name=service,
                category=category,
                is_preset=True,
                user=None,
                defaults={"is_preset": True},
            )


def unseed_presets(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    ServiceName = apps.get_model("catalog", "ServiceName")
    Subscription = apps.get_model("plans", "Subscription")
    used_category_ids = set(Subscription.objects.values_list("category_id", flat=True))
    used_service_ids = set(Subscription.objects.values_list("service_name_id", flat=True))
    ServiceName.objects.filter(is_preset=True, user=None).exclude(id__in=used_service_ids).delete()
    Category.objects.filter(is_preset=True, user=None).exclude(id__in=used_category_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0001_initial"),
        ("plans", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_presets, unseed_presets),
    ]
