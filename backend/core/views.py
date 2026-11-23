from django.db import connection

from core.ip_diagnostics import maybe_log_health_ip_diagnostics
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET", "HEAD"])
@permission_classes([AllowAny])
@throttle_classes([])
def health(request):
    maybe_log_health_ip_diagnostics(request)
    response = Response({"status": "ok"})
    response["Cache-Control"] = "no-store"
    return response


@api_view(["GET", "HEAD"])
@permission_classes([AllowAny])
@throttle_classes([])
def health_ready(request):
    """Readiness: verifies the configured default database accepts connections."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        payload = {"status": "unavailable", "database": "unavailable"}
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        payload = {"status": "ok", "database": "ok"}
        status_code = status.HTTP_200_OK
    response = Response(payload, status=status_code)
    response["Cache-Control"] = "no-store"
    return response