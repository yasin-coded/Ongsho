"""Re-seed preset catalog rows when the DB was flushed."""

from __future__ import annotations

_PRESET_CATEGORIES = [
    "Streaming",
    "Music",
    "AI tools",
    "Software",
    "Hosting",
    "Internet",
    "Utilities",
    "Other",
]

_PRESET_SERVICES = {
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


def ensure_catalog_presets():
    from catalog.models import Category, ServiceName

    if Category.objects.filter(is_preset=True, name="Streaming").exists():
        return
    for name in _PRESET_CATEGORIES:
        Category.objects.get_or_create(name=name, is_preset=True, user=None, defaults={"is_preset": True})
    for category_name, services in _PRESET_SERVICES.items():
        category = Category.objects.get(name=category_name, is_preset=True, user=None)
        for service in services:
            ServiceName.objects.get_or_create(
                name=service,
                category=category,
                is_preset=True,
                user=None,
                defaults={"is_preset": True},
            )