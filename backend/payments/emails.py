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


def send_payment_rejected_email(*, to_email: str, payload: dict) -> None:
    payer_first = str(payload.get("payer_first_name") or "").strip() or "there"
    plan_name = str(payload.get("plan_name") or "").strip() or "your plan"
    reviewer = str(payload.get("reviewer_name") or "").strip() or "The plan owner"
    amount_display = str(payload.get("amount_display") or "").strip()
    method_label = str(payload.get("method_label") or "").strip()
    transaction_id = str(payload.get("transaction_id") or "").strip()
    paid_on = str(payload.get("paid_on") or "").strip()
    rejection_reason = str(payload.get("rejection_reason") or "").strip()
    reviewed_at = str(payload.get("reviewed_at") or "").strip()
    link_path = str(payload.get("link_path") or "").strip()
    subscription_currency = str(payload.get("subscription_currency") or "").strip()

    lines = [
        f"Hi {payer_first},",
        "",
        f"{reviewer} did not confirm your payment submission for {plan_name}.",
        "",
        f"Amount: {amount_display}",
    ]
    if subscription_currency == "USD":
        lines.append("This plan is billed in USD; the amount above is your share in BDT.")
    lines.append(f"Method: {method_label}")
    if transaction_id:
        lines.append(f"Reference: {transaction_id}")
    if paid_on:
        lines.append(f"Date paid: {paid_on}")
    if rejection_reason:
        lines.extend(["", f"Reason: {rejection_reason}"])
    if reviewed_at:
        try:
            dt = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            local = timezone.localtime(dt)
            lines.append(f"Reviewed on: {local.strftime('%Y-%m-%d %H:%M')} ({settings.TIME_ZONE})")
        except (TypeError, ValueError):
            lines.append(f"Reviewed on: {reviewed_at}")
    lines.extend(
        [
            "",
            "If you need clarification, contact your cooperative's owner or administrator.",
            "",
            "View your plan:",
            f"{settings.FRONTEND_BASE_URL}{link_path}",
            "",
        ]
    )

    subject = f"Payment not confirmed — {plan_name}"
    send_mail(
        subject=subject,
        message="\n".join(lines),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
        fail_silently=False,
    )