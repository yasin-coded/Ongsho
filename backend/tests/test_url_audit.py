"""Every API route must declare explicit DRF permission_classes (architecture §15)."""

from __future__ import annotations

import pytest
from django.urls import get_resolver
from rest_framework.permissions import AllowAny

from core.url_inspection import drf_view_class, explicit_permission_classes, flatten_urlpatterns

# Auth and public invite/join flows (health endpoint to be added later).
ALLOWANY_URL_NAMES = frozenset(
    {
        "auth-register",
        "auth-login",
        "auth-refresh",
        "auth-logout",
        "auth-verify-email",
        "auth-verify-email-change",
        "auth-resend-verification",
        "auth-password-reset",
        "auth-password-reset-confirm",
        "invite-public",
        "invite-signup",
        "health",
        "health-ready",
    }
)


# Documented public plan-link routes (not on the AllowAny allowlist — use PublicEndpoint).
PLAN_JOIN_URL_NAMES = frozenset({"plan-join-public", "plan-join-signup"})


def _api_routes():
    resolver = get_resolver()
    routes = []
    for route, name, callback in flatten_urlpatterns(resolver.url_patterns):
        if not route.startswith("api/"):
            continue
        if route.startswith("api/admin") or route == "admin/" or "admin/" in route.split("/", 2)[:2]:
            continue
        routes.append((route, name, callback))
    return routes


def test_every_api_route_has_explicit_permission_classes():
    missing: list[str] = []
    wrong_allow: list[str] = []
    for route, name, callback in _api_routes():
        view_cls = drf_view_class(callback)
        if view_cls is None:
            continue
        perms = explicit_permission_classes(view_cls)
        label = f"{name or route} ({route})"
        if perms is None:
            missing.append(label)
            continue
        is_allow_any = len(perms) == 1 and perms[0] is AllowAny
        if is_allow_any and (name not in ALLOWANY_URL_NAMES):
            wrong_allow.append(label)
        if not is_allow_any and name in ALLOWANY_URL_NAMES:
            wrong_allow.append(f"{label} (expected AllowAny)")
    assert not missing, "Routes missing explicit permission_classes:\n" + "\n".join(missing)
    assert not wrong_allow, "AllowAny mismatch:\n" + "\n".join(wrong_allow)


def test_plan_join_routes_are_separate_public_endpoints():
    """GET /api/join/{token}/ and POST .../signup/ are plan-wide links, not per-invite token URLs."""
    from django.urls import get_resolver

    from core.permissions import PublicEndpoint
    from core.url_inspection import drf_view_class, explicit_permission_classes, flatten_urlpatterns

    resolver = get_resolver()
    by_name: dict[str, tuple] = {}
    for route, name, callback in flatten_urlpatterns(resolver.url_patterns):
        if name:
            by_name[name] = (route, callback)
    join_get = by_name["plan-join-public"]
    join_post = by_name["plan-join-signup"]
    invite_get = by_name["invite-public"]
    invite_signup = by_name["invite-signup"]
    assert join_get[0] == "api/join/<str:token>/"
    assert join_post[0] == "api/join/<str:token>/signup/"
    assert invite_get[0] == "api/invites/<str:token>/"
    assert invite_signup[0] == "api/invites/<str:token>/signup/"
    for _name, (_route, callback) in (("plan-join-public", join_get), ("plan-join-signup", join_post)):
        view_cls = drf_view_class(callback)
        perms = explicit_permission_classes(view_cls)
        assert perms == [PublicEndpoint]