"""DRF permissions used in security audits (distinct from AllowAny where noted)."""

from rest_framework.permissions import BasePermission


class PublicEndpoint(BasePermission):
    """Anonymous access by design (plan join links). Not part of the AllowAny allowlist audit."""

    def has_permission(self, request, view) -> bool:
        return True