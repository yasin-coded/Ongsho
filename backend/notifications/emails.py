"""Reminder email body (used by outbox dispatch only)."""

from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail


def send_reminder_email(*, to_email: str, subject: str, message: str, link_path: str) -> None:
    body = f"{message}\n\n{settings.FRONTEND_BASE_URL}{link_path}\n"
    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
        fail_silently=False,
    )