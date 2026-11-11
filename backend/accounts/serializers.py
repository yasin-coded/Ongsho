from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core import validators
from rest_framework import serializers

from accounts.constants import AVATAR_KEY_SET

User = get_user_model()

ME_PATCH_ALLOWED = frozenset({"name", "avatar_id"})


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    name = serializers.CharField(max_length=255, trim_whitespace=True)

    def validate_email(self, value: str) -> str:
        return value.strip().lower()

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("This field may not be blank.")
        return value

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value

    def validate(self, attrs):
        email = attrs["email"]
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError({"email": ["A user with this email already exists."]})
        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_email(self, value: str) -> str:
        return value.strip().lower()


class VerifyEmailSerializer(serializers.Serializer):
    token = serializers.CharField(trim_whitespace=True)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value: str) -> str:
        return value.strip().lower()


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value: str) -> str:
        return value.strip().lower()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField(trim_whitespace=True)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)


def user_public_dict(user) -> dict:
    return {
        "id": user.pk,
        "email": user.email,
        "name": user.name,
        "avatar_id": user.avatar_id,
    }


class MePatchSerializer(serializers.Serializer):
    name = serializers.CharField(
        max_length=User._meta.get_field("name").max_length,
        required=False,
        trim_whitespace=True,
    )
    avatar_id = serializers.CharField(required=False, trim_whitespace=True)

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("This field may not be blank.")
        return value

    def validate_avatar_id(self, value: str) -> str:
        value = value.strip()
        if value not in AVATAR_KEY_SET:
            raise serializers.ValidationError("Select a valid avatar.")
        return value


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)


class EmailChangeRequestSerializer(serializers.Serializer):
    new_email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_new_email(self, value: str) -> str:
        return value.strip().lower()

    def validate(self, attrs):
        user = self.context["request"].user
        new_email = attrs["new_email"]
        if new_email == user.email:
            raise serializers.ValidationError({"new_email": ["Enter a different email address."]})
        if User.objects.filter(email__iexact=new_email).exists():
            raise serializers.ValidationError(
                {"new_email": ["A user with this email already exists."]}
            )
        return attrs


class EmailChangeVerifySerializer(serializers.Serializer):
    token = serializers.CharField(trim_whitespace=True)


class ReminderSettingsPatchSerializer(serializers.Serializer):
    days_before = serializers.ListField(
        child=serializers.IntegerField(min_value=1, max_value=14),
        required=False,
        allow_empty=False,
    )
    email = serializers.BooleanField(required=False)

    def validate_days_before(self, value):
        from accounts.validators import validate_reminder_days_value_list
        from django.core.exceptions import ValidationError as DjangoValidationError

        try:
            validate_reminder_days_value_list(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages[0])
        return value
