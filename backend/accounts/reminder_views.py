from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts import services
from accounts.serializers import ReminderSettingsPatchSerializer
from core.exceptions import DomainError, ValidationFailed


def _domain_response(exc: DomainError) -> Response:
    from core.exceptions import error_response

    return error_response(exc.code, exc.message, exc.fields, exc.status_code)


def _method_not_allowed() -> Response:
    from core.exceptions import error_response

    return error_response("method_not_allowed", "Method not allowed.", {}, 405)


REMINDER_ALLOWED = frozenset({"days_before", "email"})


@api_view(["GET", "PATCH", "PUT", "POST", "DELETE"])
@permission_classes([IsAuthenticated])
def reminder_settings(request):
    if request.method in ("PUT", "POST", "DELETE"):
        return _method_not_allowed()
    if request.method == "GET":
        return Response(services.reminder_settings_dict(request.user))
    forbidden = [key for key in request.data if key not in REMINDER_ALLOWED]
    if forbidden:
        return _domain_response(
            ValidationFailed(
                "These fields cannot be changed.",
                code="field_not_editable",
                fields={f: ["This field cannot be changed."] for f in forbidden},
            )
        )
    serializer = ReminderSettingsPatchSerializer(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    if not serializer.validated_data:
        return Response(services.reminder_settings_dict(request.user))
    services.update_reminder_settings(request.user, **serializer.validated_data)
    request.user.refresh_from_db()
    return Response(services.reminder_settings_dict(request.user))
