from core.ip_diagnostics import maybe_log_health_ip_diagnostics
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