"""Helpers to walk URLconf for security audits."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from django.urls import URLPattern, URLResolver


def flatten_urlpatterns(patterns, prefix: str = "") -> Iterator[tuple[str, str | None, Any]]:
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            nested = prefix + str(pattern.pattern)
            yield from flatten_urlpatterns(pattern.url_patterns, nested)
            continue
        if not isinstance(pattern, URLPattern):
            continue
        route = prefix + str(pattern.pattern)
        yield route, pattern.name, pattern.callback


def drf_view_class(callback) -> type | None:
    view_cls = getattr(callback, "cls", None)
    if view_cls is not None:
        return view_cls
    view_cls = getattr(callback, "view_class", None)
    if view_cls is not None:
        return view_cls
    return None


def explicit_permission_classes(view_cls: type) -> list | None:
    if "permission_classes" not in view_cls.__dict__:
        return None
    return list(view_cls.permission_classes)