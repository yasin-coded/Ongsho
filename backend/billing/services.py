from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction

from audit import services as audit_services
from billing.models import Charge, ChargeStatus
from billing.selectors import schedule_for_subscription
from core.choices import Currency
from core.exceptions import ConflictError, NotFound, ValidationFailed
from core.money import quantize_money, to_bdt
from core.schedule import due_dates_between, first_bill_date, period_end_for, price_at
from core.signals import charge_amount_changed, charges_created
from plans.models import ExchangeRate, PriceChange, Subscription, SubscriptionStatus

CHARGE_LEAD_DAYS = 10


def _latest_rate(user, today) -> ExchangeRate | None:
    return (
        ExchangeRate.objects.filter(user=user, rate_date__lte=today)
        .order_by("-rate_date", "-id")
        .first()
    )


def _prices_for_plan(plan_id: int):
    return list(PriceChange.objects.filter(subscription_id=plan_id).order_by("effective_from", "id"))


def _charge_has_member_payments(charge: Charge) -> bool:
    from payments.models import PaymentAllocation

    owner_id = charge.subscription.owner_id
    return PaymentAllocation.objects.filter(
        due__charge=charge,
    ).exclude(payment__member__user_id=owner_id).exists()


@transaction.atomic
def generate_missing_charges(plan: Subscription, today) -> dict[str, int]:
    if plan.archived_on is not None:
        return {"created": 0, "errors": 0}
    if plan.status in (
        SubscriptionStatus.PAUSED,
        SubscriptionStatus.CANCELLED,
        SubscriptionStatus.EXPIRED,
    ):
        return {"created": 0, "errors": 0}

    plan = Subscription.objects.select_for_update().get(pk=plan.pk)
    schedule = schedule_for_subscription(plan)
    first = first_bill_date(plan.start_date, plan.trial_end_date)
    window_end = today + timedelta(days=CHARGE_LEAD_DAYS)
    from_date = max(plan.billing_from, first)
    if plan.status == SubscriptionStatus.TRIAL and plan.trial_end_date:
        from_date = max(from_date, plan.trial_end_date)

    due_list = [d for d in due_dates_between(schedule, from_date, window_end) if d >= plan.billing_from]

    prices = _prices_for_plan(plan.pk)
    if not prices:
        return {"created": 0, "errors": 1}

    rate_row = None
    if plan.currency == Currency.USD:
        rate_row = _latest_rate(plan.owner, today)
        if rate_row is None:
            return {"created": 0, "errors": 1}

    created_rows: list[Charge] = []
    for due in due_list:
        if Charge.objects.filter(subscription=plan, period_start=due).exists():
            continue
        amount = quantize_money(price_at(prices, due))
        rate_used = None
        amount_bdt = amount
        if plan.currency == Currency.USD:
            rate_used = rate_row.usd_to_bdt
            amount_bdt = to_bdt(amount, rate_used)
        period_end = period_end_for(schedule, due)
        locked = due <= today
        status = ChargeStatus.DUE if locked else ChargeStatus.UPCOMING
        created_rows.append(
            Charge.objects.create(
                subscription=plan,
                period_start=due,
                period_end=period_end,
                due_date=due,
                amount=amount,
                currency=plan.currency,
                rate_used=rate_used,
                amount_bdt=amount_bdt,
                status=status,
                locked=locked,
            )
        )
    if created_rows:
        charges_created.send(sender=generate_missing_charges, charges=created_rows)
    return {"created": len(created_rows), "errors": 0}


@transaction.atomic
def refresh_unlocked_charges(plan: Subscription, today) -> int:
    plan = Subscription.objects.select_for_update().get(pk=plan.pk)
    prices = _prices_for_plan(plan.pk)
    rate_row = _latest_rate(plan.owner, today) if plan.currency == Currency.USD else None
    updated = 0
    for charge in Charge.objects.filter(
        subscription=plan,
        locked=False,
        due_date__gt=today,
    ):
        amount = quantize_money(price_at(prices, charge.due_date))
        amount_bdt = amount
        rate_used = charge.rate_used
        if plan.currency == Currency.USD:
            if rate_row is None:
                continue
            rate_used = rate_row.usd_to_bdt
            amount_bdt = to_bdt(amount, rate_used)
        if charge.amount != amount or charge.amount_bdt != amount_bdt or charge.rate_used != rate_used:
            charge.amount = amount
            charge.amount_bdt = amount_bdt
            charge.rate_used = rate_used
            charge.save(update_fields=["amount", "amount_bdt", "rate_used"])
            charge_amount_changed.send(sender=refresh_unlocked_charges, charge=charge)
            updated += 1
    return updated


@transaction.atomic
def lock_due_charges(today) -> int:
    qs = Charge.objects.filter(due_date__lte=today, locked=False)
    count = 0
    for charge in qs.select_for_update():
        charge.locked = True
        if charge.status == ChargeStatus.UPCOMING:
            charge.status = ChargeStatus.DUE
        charge.save(update_fields=["locked", "status"])
        count += 1
    return count


@transaction.atomic
def expire_fixed_term_plans(today) -> int:
    from plans.models import RenewalType

    qs = Subscription.objects.filter(
        archived_on__isnull=True,
        renewal_type=RenewalType.FIXED_TERM,
        end_date__lte=today,
        status__in=(SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL),
    )
    count = 0
    for sub in qs.select_for_update():
        old = sub.status
        sub.status = SubscriptionStatus.EXPIRED
        sub.save(update_fields=["status"])
        audit_services.log(
            None,
            "plan.expired",
            "Subscription",
            sub.pk,
            {"status": old},
            {"status": sub.status},
            plan_id=sub.pk,
            summary=f"Plan expired on {sub.end_date.isoformat()}",
        )
        count += 1
    return count


@transaction.atomic
def activate_ended_trials(today) -> int:
    qs = Subscription.objects.filter(
        archived_on__isnull=True,
        status=SubscriptionStatus.TRIAL,
        trial_end_date__lte=today,
    )
    count = 0
    for sub in qs.select_for_update():
        old = sub.status
        sub.status = SubscriptionStatus.ACTIVE
        sub.save(update_fields=["status"])
        audit_services.log(
            None,
            "plan.trial_ended",
            "Subscription",
            sub.pk,
            {"status": old},
            {"status": sub.status},
            plan_id=sub.pk,
            summary=f"Trial ended on {sub.trial_end_date.isoformat()}",
        )
        count += 1
    return count


@transaction.atomic
def correct_rate(user, charge_id: int, rate: Decimal, today) -> Charge:
    from billing.selectors import owned_charge

    rate = Decimal(rate)
    if rate <= 0:
        raise ValidationFailed(
            "Rate must be greater than zero.",
            fields={"rate": ["Rate must be greater than zero."]},
        )
    q = Decimal("0.0001")
    quantized = rate.quantize(q, rounding=ROUND_HALF_UP)
    if quantized != rate:
        raise ValidationFailed(
            "Enter a number with at most 4 decimal places.",
            fields={"rate": ["Enter a number with at most 4 decimal places."]},
        )
    rate = quantized

    charge = owned_charge(user, charge_id)
    charge = Charge.objects.select_for_update().get(pk=charge.pk)
    if charge.currency != Currency.USD:
        raise ValidationFailed("Only USD charges can be corrected.", code="not_usd")
    if _charge_has_member_payments(charge):
        raise ConflictError("Payments have started for this charge.", code="payments_started")

    old_rate = charge.rate_used
    charge.rate_used = rate
    charge.amount_bdt = to_bdt(charge.amount, rate)
    charge.locked = True
    charge.save(update_fields=["rate_used", "amount_bdt", "locked"])
    month_label = charge.period_start.strftime("%B %Y")
    audit_services.log(
        user,
        "charge.rate_corrected",
        "Charge",
        charge.pk,
        {"rate_used": str(old_rate) if old_rate else None},
        {"rate_used": str(rate)},
        plan_id=charge.subscription_id,
        summary=f"You corrected the rate to {rate} for {month_label}",
    )
    charge_amount_changed.send(sender=correct_rate, charge=charge)
    return charge
