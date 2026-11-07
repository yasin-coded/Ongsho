from django.conf import settings
from django.core.mail import send_mail

from accounts.tokens import make_email_verification_token


def send_verification_email(user) -> None:
    token = make_email_verification_token(user)
    link = f"{settings.FRONTEND_BASE_URL}/verify-email?token={token}"
    send_mail(
        subject="Verify your Ongsho email",
        message=f"Open this link to verify your email:\n\n{link}\n",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )


def send_password_reset_email(user, uid: str, token: str) -> None:
    link = f"{settings.FRONTEND_BASE_URL}/reset-password?uid={uid}&token={token}"
    send_mail(
        subject="Reset your Ongsho password",
        message=f"Open this link to choose a new password:\n\n{link}\n",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
