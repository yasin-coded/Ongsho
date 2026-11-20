"""Daily reminder dispatch for owners and members."""

from __future__ import annotations

import logging
from calendar import month_name
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.validators import parse_reminder_days
from billing.models import Charge
from billing.selectors import _bdt_at, schedule_for_subscription
from core.money import format_bdt, quantize_money
from core.notify import notify
from core.schedule import due_dates_between, stop_date
from dues.models import Due, DueStatus
from notifications.models import Reminder, ReminderChannel, ReminderKind
from plans.models import PlanMode, PriceChange, RenewalType, Subscription, SubscriptionStatus
from sharing.models import Member, MemberStatus, SharedPlan
from sharing.selectors import is_owner_seat

logger = logging.getLogger(__name__)

_ACTIVE = {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}


def _when_phrase(days: int) -> str:
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    return f"in {days} days"


def _month_label(d: date) -> str:
    return month_name[d.month]


def _owner_amount(sub: Subscription, on_date: date, prices: list) -> Decimal:
    charge = Charge.objects.filter(subscription=sub, due_date=on_date).first()
    if charge is None:
        charge = Charge.objects.filter(subscription=sub, period_start=on_date).first()
    if charge:
        return quantize_money(charge.amount_bdt)
    raw = _bdt_at(sub, on_date, prices)
    return Decimal(raw) if raw else Decimal("0")


def _dispatch(
    *,
    user,
    sub: Subscription,
    charge: Charge | None,
    kind: str,
    reminder_kind: str,
    target_date: date,
    days_before: int,
    title: str,
    message: str,
    link: str,
    payload: dict,
    email_reminders: bool,
) -> tuple[bool, bool, bool]:
    """
    Create Reminder + notification; optional outbox email.

    Returns (created, email_queued, enqueue_failed). ``email_queued`` / ``enqueue_failed`` refer
    to outbox insert success or failure, not provider delivery.
    """
    from core.mail_enqueue import OutboxEnqueueError
    from core.mail_outbox import enqueue_reminder_delivery
    from core.models.outbound_email import OutboundEmail, OutboundEmailType

    email_queued = False
    email_failed = False
    with transaction.atomic():
        reminder, created = Reminder.objects.get_or_create(
            kind=reminder_kind,
            subscription=sub,
            target_date=target_date,
            days_before=days_before,
            user=user,
            defaults={
                "charge": charge,
                "channel": ReminderChannel.IN_APP,
                "sent_at": timezone.now(),
            },
        )
        needs_save = created
        if created:
            notify(user, kind, title, message, link=link, payload=payload)
            channel = ReminderChannel.IN_APP
        else:
            channel = reminder.channel

        if email_reminders and user.email_verified:
            has_outbox = OutboundEmail.objects.filter(
                reminder_id=reminder.pk,
                email_type=OutboundEmailType.REMINDER,
            ).exists()
            if not has_outbox:
                business_event_id = f"reminder:{reminder.pk}"
                try:
                    with transaction.atomic():
                        enqueue_reminder_delivery(
                            reminder=reminder,
                            user=user,
                            title=title,
                            message=message,
                            link_path=link,
                        )
                    email_queued = True
                    channel = ReminderChannel.EMAIL
                    needs_save = True
                except OutboxEnqueueError:
                    logger.warning("reminder_outbox_enqueue_failed reminder_id=%s", reminder.pk)
                    email_failed = True
                    if created:
                        needs_save = True
                except IntegrityError:
                    if OutboundEmail.objects.filter(
                        reminder_id=reminder.pk,
                        email_type=OutboundEmailType.REMINDER,
                        business_event_id=business_event_id,
                    ).exists():
                        email_queued = True
                        channel = ReminderChannel.EMAIL
                        needs_save = True
                    else:
                        logger.warning("reminder_outbox_enqueue_integrity_failure reminder_id=%s", reminder.pk)
                        email_failed = True
                        if created:
                            needs_save = True
        elif created:
            channel = ReminderChannel.IN_APP
            needs_save = True

        if needs_save:
            reminder.channel = channel
            reminder.sent_at = timezone.now()
            reminder.save(update_fields=["channel", "sent_at"])
    return created, email_queued, email_failed


def _owner_targets(sub: Subscription, today: date, prices: list) -> list[tuple[str, date, str, str, str, dict]]:
    """Return tuples (notif_kind, target, title, message, link, payload)."""
    try:
        shared = sub.shared_plan
    except SharedPlan.DoesNotExist:
        shared = None
    is_shared = shared is not None
    items: list[tuple[str, date, str, str, str, dict]] = []
    schedule = schedule_for_subscription(sub)
    end = stop_date(schedule) or (today + timedelta(days=366 * 3))
    dates = [d for d in due_dates_between(schedule, today, end) if d >= today and d >= sub.billing_from]
    if sub.status in _ACTIVE and dates:
        target = dates[0]
        amount = _owner_amount(sub, target, prices)
        members_note = " Members have been reminded." if is_shared else ""
        items.append(
            (
                "renewal",
                target,
                f"{sub.plan_name} renews {_when_phrase((target - today).days)}",
                f"Pay {sub.plan_name} {format_bdt(amount)} to the provider.{members_note}",
                f"/app/plans/{sub.pk}",
                {"plan_id": sub.pk},
            )
        )
    if sub.status == SubscriptionStatus.TRIAL and sub.trial_end_date and sub.trial_end_date >= today:
        target = sub.trial_end_date
        items.append(
            (
                "trial_end",
                target,
                f"{sub.plan_name}'s trial ends {_when_phrase((target - today).days)}",
                f"Charging starts on {target.isoformat()}. Cancel before then if you do not want to continue.",
                f"/app/plans/{sub.pk}",
                {"plan_id": sub.pk},
            )
        )
    if (
        sub.status == SubscriptionStatus.ACTIVE
        and sub.renewal_type == RenewalType.FIXED_TERM
        and sub.end_date
        and sub.end_date >= today
    ):
        target = sub.end_date
        items.append(
            (
                "expiry",
                target,
                f"{sub.plan_name} expires {_when_phrase((target - today).days)}",
                "It will not renew by itself. Renew it if you want to keep it.",
                f"/app/plans/{sub.pk}",
                {"plan_id": sub.pk},
            )
        )
    return items


def _member_due_items(member: Member, today: date) -> list[tuple[Due, int]]:
    sub = member.shared_plan.subscription
    if sub.archived_on or sub.owner_id == member.user_id:
        return []
    if sub.status not in _ACTIVE:
        return []
    if member.status not in (MemberStatus.ACTIVE, MemberStatus.LEAVE_REQUESTED):
        return []
    if member.left_on and member.left_on < today:
        return []
    open_dues = (
        Due.objects.filter(member=member, status=DueStatus.DUE, charge__subscription=sub)
        .select_related("charge")
        .order_by("charge__due_date", "id")
    )
    out = []
    for due in open_dues:
        if is_owner_seat(member):
            continue
        due_date = due.charge.due_date
        if due_date < today:
            continue
        days = (due_date - today).days
        out.append((due, days))
    return out


def send_reminders(today: date) -> dict[str, int]:
    """
    Daily reminder job.

    Counter semantics: ``emails_sent`` counts reminder emails successfully enqueued to the
    outbox; ``emails_failed`` counts enqueue failures. Neither reflects worker/provider delivery.
    """
    User = get_user_model()
    counts = {
        "owner_reminders": 0,
        "member_reminders": 0,
        "emails_sent": 0,
        "emails_failed": 0,
    }
    kind_map = {
        "renewal": ReminderKind.RENEWAL,
        "trial_end": ReminderKind.TRIAL_END,
        "expiry": ReminderKind.EXPIRY,
        "due_soon": ReminderKind.DUE_SOON,
    }
    for user in User.objects.all().iterator():
        days_list = parse_reminder_days(user.reminder_days)
        if not days_list:
            continue
        email_on = user.email_reminders
        owned = (
            Subscription.objects.filter(owner=user, archived_on__isnull=True, status__in=_ACTIVE)
            .select_related("shared_plan")
        )
        for sub in owned:
            prices = list(PriceChange.objects.filter(subscription=sub).order_by("effective_from", "id"))
            for notif_kind, target, title, message, link, payload in _owner_targets(sub, today, prices):
                gap = (target - today).days
                if gap not in days_list:
                    continue
                charge = Charge.objects.filter(subscription=sub, period_start=target).first()
                if charge is None:
                    charge = Charge.objects.filter(subscription=sub, due_date=target).first()
                created, emailed, failed = _dispatch(
                    user=user,
                    sub=sub,
                    charge=charge,
                    kind=notif_kind,
                    reminder_kind=kind_map[notif_kind],
                    target_date=target,
                    days_before=gap,
                    title=title,
                    message=message,
                    link=link,
                    payload=payload,
                    email_reminders=email_on,
                )
                if created:
                    counts["owner_reminders"] += 1
                if emailed:
                    counts["emails_sent"] += 1
                if failed:
                    counts["emails_failed"] += 1

        memberships = (
            Member.objects.filter(
                user=user,
                status__in=(MemberStatus.ACTIVE, MemberStatus.LEAVE_REQUESTED),
            )
            .exclude(shared_plan__subscription__owner=user)
            .select_related("shared_plan__subscription", "user")
        )
        for member in memberships:
            for due, gap in _member_due_items(member, today):
                if gap not in days_list:
                    continue
                sub = member.shared_plan.subscription
                open_dues = list(
                    Due.objects.filter(member=member, status=DueStatus.DUE, charge__subscription=sub).select_related(
                        "charge"
                    )
                )
                total = quantize_money(sum((d.amount_bdt for d in open_dues), Decimal("0")))
                earlier = [d for d in open_dues if d.charge.due_date < due.charge.due_date]
                suffix = ""
                if earlier:
                    names = sorted({_month_label(d.charge.due_date) for d in earlier})
                    suffix = f" That includes {', '.join(names)}."
                title = f"{sub.plan_name} is due {_when_phrase(gap)}"
                message = f"You owe {format_bdt(total)}.{suffix}"
                payload = {"plan_id": sub.pk, "due_ids": [d.pk for d in open_dues]}
                created, emailed, failed = _dispatch(
                    user=user,
                    sub=sub,
                    charge=due.charge,
                    kind="due_soon",
                    reminder_kind=ReminderKind.DUE_SOON,
                    target_date=due.charge.due_date,
                    days_before=gap,
                    title=title,
                    message=message,
                    link=f"/app/shared/{sub.pk}",
                    payload=payload,
                    email_reminders=email_on,
                )
                if created:
                    counts["member_reminders"] += 1
                if emailed:
                    counts["emails_sent"] += 1
                if failed:
                    counts["emails_failed"] += 1
    return counts
