from django.conf import settings
from django.core.mail import send_mail

from accounts.tokens import make_email_change_token, make_email_verification_token


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


def send_email_change_verification(user, new_email: str) -> None:
    token = make_email_change_token(user, new_email)
    link = f"{settings.FRONTEND_BASE_URL}/verify-email?type=email-change&token={token}"
    send_mail(
        subject="Verify your new Ongsho email",
        message=f"Open this link to confirm your new email address:\n\n{link}\n",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[new_email],
        fail_silently=False,
    )


def send_password_changed_notice_email(*, to_email: str, payload: dict) -> None:
    occurred = str(payload.get("occurred_at") or "").strip()
    link_path = str(payload.get("link_path") or "/app/profile").strip()
    lines = [
        "Hi,",
        "",
        "Your Ongsho password was changed.",
        "",
        "If you made this change, you can ignore this message.",
        "If you did not change your password, secure your account and contact support.",
        "",
        f"View your profile: {settings.FRONTEND_BASE_URL}{link_path}",
    ]
    if occurred:
        lines.insert(3, f"When: {occurred}")
    send_mail(
        subject="Your Ongsho password was changed",
        message="\n".join(lines),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
        fail_silently=False,
    )


def send_password_reset_completed_notice_email(*, to_email: str, payload: dict) -> None:
    occurred = str(payload.get("occurred_at") or "").strip()
    link_path = str(payload.get("link_path") or "/app/profile").strip()
    lines = [
        "Hi,",
        "",
        "Your Ongsho password was reset using the reset link.",
        "",
        "If you reset your password, you can ignore this message.",
        "If you did not request a reset, secure your account and contact support.",
        "",
        f"View your profile: {settings.FRONTEND_BASE_URL}{link_path}",
    ]
    if occurred:
        lines.insert(3, f"When: {occurred}")
    send_mail(
        subject="Your Ongsho password was reset",
        message="\n".join(lines),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
        fail_silently=False,
    )


def send_email_changed_new_notice_email(*, to_email: str, payload: dict) -> None:
    occurred = str(payload.get("occurred_at") or "").strip()
    link_path = str(payload.get("link_path") or "/app/profile").strip()
    new_email = str(payload.get("new_email") or "").strip()
    lines = [
        "Hi,",
        "",
        "Your Ongsho sign-in email was updated.",
        "",
        f"You now sign in with {new_email}." if new_email else "Your new sign-in address is active.",
        "",
        f"View your profile: {settings.FRONTEND_BASE_URL}{link_path}",
    ]
    if occurred:
        lines.insert(3, f"When: {occurred}")
    send_mail(
        subject="Your Ongsho sign-in email was updated",
        message="\n".join(lines),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
        fail_silently=False,
    )


def send_email_changed_previous_notice_email(*, to_email: str, payload: dict) -> None:
    occurred = str(payload.get("occurred_at") or "").strip()
    link_path = str(payload.get("link_path") or "/app/profile").strip()
    new_email = str(payload.get("new_email") or "").strip()
    lines = [
        "Hi,",
        "",
        "The sign-in email on your Ongsho account was changed.",
        "",
        f"The account no longer uses this address ({to_email}).",
    ]
    if new_email:
        lines.append(f"The new sign-in address is {new_email}.")
    lines.extend(
        [
            "",
            "If you made this change, you can ignore this message.",
            "If you did not change your email, secure your account and contact support.",
            "",
            f"View your profile: {settings.FRONTEND_BASE_URL}{link_path}",
        ]
    )
    if occurred:
        lines.insert(3, f"When: {occurred}")
    send_mail(
        subject="Your Ongsho sign-in email was changed",
        message="\n".join(lines),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
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
