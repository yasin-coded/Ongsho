"""Payment receipt email (outbox dispatch only)."""

from __future__ import annotations

from datetime import datetime

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone


def send_payment_receipt_email(*, to_email: str, payload: dict) -> None:
    payer_first = str(payload.get("payer_first_name") or "").strip() or "there"
    plan_name = str(payload.get("plan_name") or "").strip() or "your plan"
    confirmer = str(payload.get("confirmer_name") or "").strip() or "The plan owner"
    amount_display = str(payload.get("amount_display") or "").strip()
    method_label = str(payload.get("method_label") or "").strip()
    transaction_id = str(payload.get("transaction_id") or "").strip()
    paid_on = str(payload.get("paid_on") or "").strip()
    covered_months = str(payload.get("covered_months") or "").strip()
    confirmed_at = str(payload.get("confirmed_at") or "").strip()
    link_path = str(payload.get("link_path") or "").strip()
    subscription_currency = str(payload.get("subscription_currency") or "").strip()

    lines = [
        f"Hi {payer_first},",
        "",
        f"{confirmer} confirmed your payment for {plan_name}.",
        "",
        f"Amount: {amount_display}",
    ]
    if subscription_currency == "USD":
        lines.append("This plan is billed in USD; the amount above is your share in BDT.")
    lines.extend(
        [
            f"Method: {method_label}",
        ]
    )
    if transaction_id:
        lines.append(f"Reference: {transaction_id}")
    if paid_on:
        lines.append(f"Date paid: {paid_on}")
    else:
        lines.append("Date paid: Not specified")
    if covered_months:
        lines.append(f"Coverage: {covered_months}")
    if confirmed_at:
        try:
            dt = datetime.fromisoformat(confirmed_at.replace("Z", "+00:00"))
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            local = timezone.localtime(dt)
            lines.append(f"Confirmed on: {local.strftime('%Y-%m-%d %H:%M')} ({settings.TIME_ZONE})")
        except (TypeError, ValueError):
            lines.append(f"Confirmed on: {confirmed_at}")
    lines.extend(
        [
            "",
            "View your plan:",
            f"{settings.FRONTEND_BASE_URL}{link_path}",
            "",
        ]
    )

    subject = f"Payment confirmed — {plan_name}"
    send_mail(
        subject=subject,
        message="\n".join(lines),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
        fail_silently=False,
    )