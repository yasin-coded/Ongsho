from __future__ import annotations

import importlib

from django.conf import settings
from django.test import override_settings


@override_settings(ADMIN_ENABLED=False)
def test_admin_routes_absent_when_disabled():
    assert settings.ADMIN_ENABLED is False
    import config.urls as urls_mod

    importlib.reload(urls_mod)
    try:
        routes = [getattr(p.pattern, "_route", str(p.pattern)) for p in urls_mod.urlpatterns]
        assert not any(r.startswith("admin/") for r in routes)
    finally:
        importlib.reload(urls_mod)