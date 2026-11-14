from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts import services
from accounts.cookies import REFRESH_COOKIE_NAME, clear_refresh_cookie, set_refresh_cookie
from accounts.serializers import (
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    ResendVerificationSerializer,
    VerifyEmailSerializer,
    user_public_dict,
)
from core.exceptions import DomainError, ValidationFailed
from core.security import require_same_app_request
from core.throttles import (
    LoginEmailThrottle,
    LoginIpThrottle,
    PasswordResetConfirmIpThrottle,
    PasswordResetRequestEmailThrottle,
    PasswordResetRequestIpThrottle,
    RefreshIpThrottle,
    RegisterIpThrottle,
    ResendVerificationEmailThrottle,
    ResendVerificationIpThrottle,
    VerifyEmailIpThrottle,
    client_ip,
)


def _domain_response(exc: DomainError, *, clear_refresh: bool = False) -> Response:
    from core.exceptions import domain_error_response

    resp = domain_error_response(exc)
    if clear_refresh:
        clear_refresh_cookie(resp)
    return resp


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([RegisterIpThrottle])
def register_view(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    try:
        services.register_user(email=data["email"], password=data["password"], name=data["name"])
    except DomainError as exc:
        return _domain_response(exc)
    return Response({"message": services.REGISTER_MESSAGE}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([VerifyEmailIpThrottle])
def verify_email_view(request):
    serializer = VerifyEmailSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        services.verify_email(serializer.validated_data["token"])
    except DomainError as exc:
        return _domain_response(exc)
    return Response({"message": "Email verified."})


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginIpThrottle, LoginEmailThrottle])
def login_view(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    try:
        access, refresh, user = services.login_user(
            email=data["email"],
            password=data["password"],
            client_ip=client_ip(request),
        )
    except DomainError as exc:
        return _domain_response(exc)
    response = Response({"access": access, "user": user_public_dict(user)}, status=status.HTTP_200_OK)
    set_refresh_cookie(response, refresh)
    return response


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([RefreshIpThrottle])
def refresh_view(request):
    try:
        require_same_app_request(request)
    except DomainError as exc:
        return _domain_response(exc)

    refresh_raw = request.COOKIES.get(REFRESH_COOKIE_NAME)
    try:
        access, refresh = services.rotate_refresh(refresh_raw)
    except DomainError as exc:
        return _domain_response(exc, clear_refresh=True)
    response = Response({"access": access}, status=status.HTTP_200_OK)
    set_refresh_cookie(response, refresh)
    return response


@api_view(["POST"])
@permission_classes([AllowAny])
def logout_view(request):
    try:
        require_same_app_request(request)
    except DomainError as exc:
        return _domain_response(exc)

    services.logout_refresh(request.COOKIES.get(REFRESH_COOKIE_NAME))
    response = Response(status=status.HTTP_204_NO_CONTENT)
    clear_refresh_cookie(response)
    return response


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([ResendVerificationIpThrottle, ResendVerificationEmailThrottle])
def resend_verification_view(request):
    serializer = ResendVerificationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    services.resend_verification(serializer.validated_data["email"])
    return Response({"message": services.RESEND_VERIFICATION_MESSAGE})


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([PasswordResetRequestIpThrottle, PasswordResetRequestEmailThrottle])
def password_reset_view(request):
    serializer = PasswordResetRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    services.request_password_reset(serializer.validated_data["email"])
    return Response({"message": services.PASSWORD_RESET_GENERIC_MESSAGE})


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([PasswordResetConfirmIpThrottle])
def password_reset_confirm_view(request):
    serializer = PasswordResetConfirmSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    uid = serializer.validated_data["uid"]
    token = serializer.validated_data["token"]
    new_password = serializer.validated_data["new_password"]

    try:
        user = services.user_for_password_reset_check(uid, token)
    except DomainError as exc:
        return _domain_response(exc)

    try:
        validate_password(new_password, user=user)
    except DjangoValidationError as exc:
        return _domain_response(
            ValidationFailed(
                exc.messages[0] if exc.messages else "Password does not meet requirements.",
                fields={"new_password": list(exc.messages)},
            )
        )

    try:
        services.confirm_password_reset(uid=uid, token=token, new_password=new_password)
    except DomainError as exc:
        return _domain_response(exc)
    return Response({"message": "Password updated."})
