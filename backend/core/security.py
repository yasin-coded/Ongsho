from django.conf import settings
from django.http import HttpRequest

from core.exceptions import Forbidden

APP_HEADER = "HTTP_X_REQUESTED_WITH"
APP_HEADER_VALUE = "Ongsho"
ORIGIN_HEADER = "HTTP_ORIGIN"


def require_same_app_request(request: HttpRequest) -> None:
    origin = request.META.get(ORIGIN_HEADER)
    if origin:
        allowed = set(settings.CORS_ALLOWED_ORIGINS)
        if origin not in allowed:
            raise Forbidden("Request origin is not allowed.", code="bad_origin")
        return
    if request.META.get(APP_HEADER) != APP_HEADER_VALUE:
        raise Forbidden("Missing or invalid application header.", code="missing_app_header")
