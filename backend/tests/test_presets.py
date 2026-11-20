import pytest

from catalog.models import Category, ServiceName


@pytest.mark.django_db
def test_preset_catalog_counts():
    assert Category.objects.filter(is_preset=True, user=None).count() == 8
    assert ServiceName.objects.filter(is_preset=True, user=None).count() == 34
    ai = Category.objects.get(name="AI tools", is_preset=True, user=None)
    assert ServiceName.objects.filter(name="Cursor", category=ai, is_preset=True).exists()
