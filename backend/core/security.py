from django.http import HttpRequest

from core.exceptions import Forbidden

APP_HEADER = "HTTP_X_REQUESTED_WITH"
APP_HEADER_VALUE = "Ongsho"


def require_same_app_request(request: HttpRequest) -> None:
    if request.META.get(APP_HEADER) != APP_HEADER_VALUE:
        raise Forbidden("Missing or invalid application header.", code="missing_app_header")
