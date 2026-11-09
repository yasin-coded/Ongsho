from django.conf import settings
from django.core import signing

EMAIL_VERIFY_SALT = "accounts.email-verify"
EMAIL_CHANGE_SALT = "accounts.email-change"


def make_email_verification_token(user) -> str:
    return signing.dumps({"user_id": user.pk, "email": user.email}, salt=EMAIL_VERIFY_SALT)


def load_email_verification_token(token: str) -> dict:
    max_age = int(settings.EMAIL_VERIFY_MAX_AGE.total_seconds())
    return signing.loads(token, salt=EMAIL_VERIFY_SALT, max_age=max_age)


def make_email_change_token(user, new_email: str) -> str:
    return signing.dumps({"user_id": user.pk, "email": new_email.lower()}, salt=EMAIL_CHANGE_SALT)


def load_email_change_token(token: str) -> dict:
    max_age = int(settings.EMAIL_VERIFY_MAX_AGE.total_seconds())
    return signing.loads(token, salt=EMAIL_CHANGE_SALT, max_age=max_age)
