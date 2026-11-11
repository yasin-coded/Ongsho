from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts import selectors, services
from accounts.cookies import clear_refresh_cookie
from accounts.serializers import (
    EmailChangeRequestSerializer,
    EmailChangeVerifySerializer,
    ME_PATCH_ALLOWED,
    MePatchSerializer,
    PasswordChangeSerializer,
)
from core.exceptions import DomainError, ValidationFailed


def _domain_response(exc: DomainError, *, clear_refresh: bool = False) -> Response:
    from core.exceptions import error_response

    resp = error_response(exc.code, exc.message, exc.fields, exc.status_code)
    if clear_refresh:
        clear_refresh_cookie(resp)
    return resp


def _method_not_allowed() -> Response:
    from core.exceptions import error_response

    return error_response("method_not_allowed", "Method not allowed.", {}, 405)


@api_view(["GET", "PATCH", "PUT", "DELETE"])
@permission_classes([IsAuthenticated])
def me_profile(request):
    if request.method == "PUT":
        return _method_not_allowed()
    if request.method == "DELETE":
        return _method_not_allowed()
    if request.method == "GET":
        return Response(services.profile_dict(request.user))
    forbidden = [key for key in request.data if key not in ME_PATCH_ALLOWED]
    if forbidden:
        return _domain_response(
            ValidationFailed(
                "These fields cannot be changed.",
                code="field_not_editable",
                fields={f: ["This field cannot be changed."] for f in forbidden},
            )
        )
    serializer = MePatchSerializer(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    if not serializer.validated_data:
        return Response(services.profile_dict(request.user))
    user = services.update_profile(request.user, serializer.validated_data)
    user.refresh_from_db()
    return Response(services.profile_dict(user))


@api_view(["POST", "GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def me_password(request):
    if request.method != "POST":
        return _method_not_allowed()
    serializer = PasswordChangeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    try:
        validate_password(data["new_password"], user=request.user)
    except DjangoValidationError as exc:
        return _domain_response(
            ValidationFailed(
                exc.messages[0] if exc.messages else "Password does not meet requirements.",
                fields={"new_password": list(exc.messages)},
            )
        )
    try:
        services.change_password(
            request.user,
            current_password=data["current_password"],
            new_password=data["new_password"],
        )
    except DomainError as exc:
        return _domain_response(exc)
    response = Response(
        {"message": "Password updated. Please sign in again."},
        status=status.HTTP_200_OK,
    )
    clear_refresh_cookie(response)
    return response


@api_view(["POST", "DELETE", "GET", "PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def me_email(request):
    if request.method in ("GET", "PUT", "PATCH"):
        return _method_not_allowed()
    if request.method == "DELETE":
        services.cancel_email_change(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
    serializer = EmailChangeRequestSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    try:
        services.request_email_change(
            request.user,
            new_email=serializer.validated_data["new_email"],
            password=serializer.validated_data["password"],
        )
    except DomainError as exc:
        return _domain_response(exc)
    return Response(
        {"message": "Check your new email inbox to confirm the address change."},
        status=status.HTTP_200_OK,
    )


@api_view(["POST", "GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def me_email_verify(request):
    if request.method != "POST":
        return _method_not_allowed()
    serializer = EmailChangeVerifySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        user = services.verify_email_change(request.user, serializer.validated_data["token"])
    except DomainError as exc:
        return _domain_response(exc)
    response = Response(
        {
            "email": user.email,
            "message": "Email updated. Please sign in again.",
        },
        status=status.HTTP_200_OK,
    )
    clear_refresh_cookie(response)
    return response


@api_view(["POST", "GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def me_email_resend(request):
    if request.method != "POST":
        return _method_not_allowed()
    try:
        services.resend_pending_email_change(request.user)
    except DomainError as exc:
        return _domain_response(exc)
    return Response(
        {"message": "If a pending change exists, a verification email was sent to that address."},
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me_nav_counts(request):
    return Response(selectors.nav_counts(request.user))
