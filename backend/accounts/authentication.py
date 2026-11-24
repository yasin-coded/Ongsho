"""JWT authentication aligned with login and refresh (active accounts only)."""

from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


class InactiveUserTokenError(AuthenticationFailed):
    default_detail = "Invalid token."
    default_code = "invalid_token"


class ActiveUserJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if not user.is_active:
            raise InactiveUserTokenError()
        return user