from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from audit import services as audit_services
from catalog.selectors import category_visible_to_user
from core.dates import today_dhaka
from core.exceptions import ConflictError, NotFound, ValidationFailed
from core.money import quantize_money, to_bdt
from payments.models import Payment, ReviewStatus
from plans.models import ExchangeRate, PriceChange, RenewalType, Subscription, SubscriptionStatus
from plans.selectors import current_amount_for_subscription, owned_subscription, service_name_for_user


def _lock_owned_subscription(user, pk: int) -> Subscription:
    sub = (
        Subscription.objects.select_for_update()
        .filter(owner=user, pk=pk, archived_on__isnull=True)
        .first()
    )
    if sub is None:
        raise NotFound("Plan not found.")
    return sub


def _status_for_trial_rule(sub: Subscription) -> str:
    today = today_dhaka()
    trial_end = sub.trial_end_date
    if trial_end and today < trial_end:
        return SubscriptionStatus.TRIAL
    return SubscriptionStatus.ACTIVE


def _plan_audit(
    user,
    action: str,
    entity_type: str,
    entity_id: int,
    old,
    new,
    sub: Subscription,
    summary: str,
    *,
    amount: Decimal | None = None,
) -> None:
    audit_services.log(
        user,
        action,
        entity_type,
        entity_id,
        old,
        new,
        plan_id=sub.pk,
        summary=summary,
        amount=amount,
    )


def void_untouched_charges_on_or_after(subscription: Subscription, from_date) -> None:
    from billing.models import Charge
    from dues.models import DueStatus

    owner_id = subscription.owner_id
    charges = (
        Charge.objects.filter(subscription=subscription, due_date__gte=from_date)
        .prefetch_related("dues__member__user")
        .order_by("id")
    )
    for charge in charges:
        dues = list(charge.dues.all())
        if dues and not all(
            due.status == DueStatus.DUE or due.member.user_id == owner_id for due in dues
        ):
            continue
        charge.delete()


def void_upcoming_untouched_charges(subscription: Subscription) -> None:
    void_untouched_charges_on_or_after(subscription, today_dhaka() + __import__("datetime").timedelta(days=1))


def _schedule_for(sub: Subscription):
    from billing.selectors import schedule_for_subscription

    return schedule_for_subscription(sub)


def _emit_status_changed(sub: Subscription) -> None:
    from core.signals import plan_status_changed

    plan_status_changed.send(sender=type(sub), plan=sub)


def _emit_prices_changed(sub: Subscription) -> None:
    from core.signals import plan_prices_changed

    plan_prices_changed.send(sender=type(sub), plan=sub)


def _invalid_status_change(sub: Subscription, action: str) -> None:
    raise ConflictError(
        f"Cannot {action} a plan that is {sub.status}.",
        code="invalid_status_change",
    )


def _quantize_rate(value: Decimal) -> Decimal:
    from decimal import ROUND_HALF_UP

    q = Decimal("0.0001")
    return Decimal(value).quantize(q, rounding=ROUND_HALF_UP)


@transaction.atomic
def create_subscription(user, validated: dict) -> tuple[Subscription, str | None]:
    service_name = service_name_for_user(user, validated["service_name_id"])
    if service_name is None:
        raise ValidationFailed(
            "Select a valid service name.",
            fields={"service_name": ["Select a valid service name."]},
        )
    category = validated.get("category")
    if category is None:
        category = service_name.category
    elif category_visible_to_user(user, category.pk) is None:
        raise ValidationFailed(
            "Select a valid category.",
            fields={"category": ["Select a valid category."]},
        )

    today = today_dhaka()
    trial_end = validated.get("trial_end_date")
    start_date = validated["start_date"]
    next_renewal = validated.get("next_renewal_date")
    if next_renewal is not None:
        if trial_end or start_date > today:
            raise ValidationFailed(
                "Next renewal date is not allowed for future-start or trial plans.",
                fields={"next_renewal_date": ["Not allowed with a future start date or trial."]},
            )
        from core.schedule import Schedule, validate_next_renewal

        draft = Schedule(
            start_date=start_date,
            trial_end_date=trial_end,
            anchor_day=start_date.day,
            cycle_unit=validated["cycle_unit"],
            cycle_count=validated["cycle_count"],
            renewal_type=validated["renewal_type"],
            end_date=validated.get("end_date"),
        )
        if not validate_next_renewal(draft, next_renewal, today):
            raise ValidationFailed(
                "Next renewal date does not match the billing schedule.",
                code="next_renewal_mismatch",
                fields={"next_renewal_date": ["Next renewal date does not match the billing schedule."]},
            )
        billing_from = next_renewal
        anchor_day = next_renewal.day
    else:
        from core.schedule import first_bill_date

        billing_from = first_bill_date(start_date, trial_end)
        anchor_day = billing_from.day
    status = (
        SubscriptionStatus.TRIAL
        if trial_end and today < trial_end
        else SubscriptionStatus.ACTIVE
    )
    sub = Subscription.objects.create(
        owner=user,
        service_name=service_name,
        category=category,
        plan_name=validated["plan_name"],
        plan_mode=validated["plan_mode"],
        note=validated.get("note", ""),
        currency=validated["currency"],
        cycle_unit=validated["cycle_unit"],
        cycle_count=validated["cycle_count"],
        anchor_day=anchor_day,
        start_date=start_date,
        trial_end_date=trial_end,
        renewal_type=validated["renewal_type"],
        end_date=validated.get("end_date"),
        status=status,
        recommended_method=validated["recommended_method"],
        rarely_used=validated.get("rarely_used", False),
        billing_from=billing_from,
    )
    amount = quantize_money(validated["amount"])
    PriceChange.objects.create(
        subscription=sub,
        amount=amount,
        currency=sub.currency,
        effective_from=start_date,
    )
    amount_bdt_preview = None
    if sub.currency == "USD":
        rate = _quantize_rate(validated["exchange_rate"])
        ExchangeRate.objects.create(
            user=user,
            rate_date=today,
            usd_to_bdt=rate,
            source="manual",
        )
        amount_bdt_preview = str(to_bdt(amount, rate))
    _plan_audit(
        user,
        "plan.created",
        "Subscription",
        sub.pk,
        None,
        {"id": sub.pk, "plan_name": sub.plan_name, "currency": sub.currency},
        sub,
        f"You created {sub.plan_name}",
    )
    _emit_status_changed(sub)
    return sub, amount_bdt_preview


@transaction.atomic
def apply_next_renewal_date(user, pk: int, target) -> Subscription:
    from core.schedule import validate_next_renewal

    sub = _lock_owned_subscription(user, pk)
    if sub.status != SubscriptionStatus.ACTIVE:
        raise ConflictError(
            "Next renewal date can only be set on active plans.",
            code="invalid_status_change",
        )
    today = today_dhaka()
    if not validate_next_renewal(_schedule_for(sub), target, today):
        raise ValidationFailed(
            "Next renewal date does not match the billing schedule.",
            code="next_renewal_mismatch",
            fields={"next_renewal_date": ["Next renewal date does not match the billing schedule."]},
        )
    old = {"anchor_day": sub.anchor_day, "billing_from": sub.billing_from.isoformat()}
    sub.anchor_day = target.day
    sub.billing_from = target
    void_untouched_charges_on_or_after(sub, target)
    sub.save(update_fields=["anchor_day", "billing_from"])
    _plan_audit(
        user,
        "plan.next_renewal",
        "Subscription",
        sub.pk,
        old,
        {"anchor_day": sub.anchor_day, "billing_from": sub.billing_from.isoformat()},
        sub,
        f"You changed the next renewal date to {target.isoformat()}",
    )
    return sub


@transaction.atomic
def update_subscription(user, pk: int, validated: dict) -> Subscription:
    sub = owned_subscription(user, pk)

    def _snap(fields):
        out = {}
        for k in fields:
            val = getattr(sub, k)
            if hasattr(val, "pk"):
                out[k] = val.pk
            elif hasattr(val, "isoformat"):
                out[k] = val.isoformat()
            else:
                out[k] = val
        return out

    if "next_renewal_date" in validated:
        return apply_next_renewal_date(user, pk, validated.pop("next_renewal_date"))
    old_snapshot = _snap(validated.keys())
    if "service_name" in validated:
        sn = service_name_for_user(user, validated["service_name"].pk)
        if sn is None:
            raise ValidationFailed(
                "Select a valid service name.",
                fields={"service_name": ["Select a valid service name."]},
            )
        sub.service_name = sn
    if "category" in validated:
        cat = validated["category"]
        if category_visible_to_user(user, cat.pk) is None:
            raise ValidationFailed(
                "Select a valid category.",
                fields={"category": ["Select a valid category."]},
            )
        sub.category = cat
    if validated.get("renewal_type") == RenewalType.AUTO:
        sub.end_date = None
    for field in ("plan_name", "note", "recommended_method", "rarely_used", "renewal_type", "end_date"):
        if field in validated:
            setattr(sub, field, validated[field])
    sub.save()
    new_snapshot = _snap(validated.keys())
    _plan_audit(
        user,
        "plan.updated",
        "Subscription",
        sub.pk,
        old_snapshot,
        new_snapshot,
        sub,
        "You edited the plan details",
    )
    return sub


def _plan_has_confirmed_or_reversed_payment(sub: Subscription) -> bool:
    from sharing.models import SharedPlan

    shared = (
        SharedPlan.objects.filter(subscription_id=sub.pk).first()
    )
    if shared is None:
        return False
    return Payment.objects.filter(
        shared_plan=shared,
        review_status__in=(ReviewStatus.CONFIRMED, ReviewStatus.REVERSED),
    ).exists()


@transaction.atomic
def delete_subscription(user, pk: int, password: str) -> None:
    if not password:
        raise ValidationFailed(
            "Enter your password.",
            code="invalid_password",
            fields={"password": ["Enter your password."]},
        )
    if not user.check_password(password):
        raise ValidationFailed(
            "The password is not correct.",
            code="invalid_password",
            fields={"password": ["The password is not correct."]},
        )
    sub = Subscription.objects.select_for_update().filter(owner=user, pk=pk).first()
    if sub is None:
        raise NotFound("Plan not found.")
    archive = _plan_has_confirmed_or_reversed_payment(sub)
    entity_id = sub.pk
    snapshot = {"id": sub.pk, "plan_name": sub.plan_name}
    if archive:
        sub.archived_on = timezone.now()
        sub.save(update_fields=["archived_on"])
        # TODO: notify all members, cancel pending invites and ownership transfers.
        audit_services.log(
            user,
            "plan.archived",
            "Subscription",
            entity_id,
            snapshot,
            None,
            plan_id=entity_id,
            summary=f"You archived {sub.plan_name}",
        )
    else:
        plan_id = entity_id
        audit_services.log(
            user,
            "plan.deleted",
            "Subscription",
            entity_id,
            snapshot,
            None,
            plan_id=plan_id,
            summary=f"You deleted {sub.plan_name}",
        )
        sub.delete()


@transaction.atomic
def add_price_change(
    user,
    pk: int,
    *,
    amount: Decimal,
    effective_from,
    exchange_rate: Decimal | None = None,
) -> tuple[PriceChange, bool]:
    sub = owned_subscription(user, pk)
    today = today_dhaka()
    if effective_from < today:
        raise ValidationFailed(
            "Effective date cannot be before today.",
            fields={"effective_from": ["Effective date cannot be before today."]},
        )
    amount = quantize_money(amount)
    if sub.currency == "BDT" and exchange_rate is not None:
        raise ValidationFailed(
            "Exchange rate must not be sent for BDT plans.",
            fields={"exchange_rate": ["Exchange rate must not be sent for BDT plans."]},
        )
    if sub.currency == "USD" and exchange_rate is not None:
        rate = _quantize_rate(exchange_rate)
        ExchangeRate.objects.create(
            user=user,
            rate_date=today,
            usd_to_bdt=rate,
            source="manual",
        )

    existing = PriceChange.objects.filter(subscription=sub, effective_from=effective_from).first()
    created = existing is None
    if existing:
        old_amount = existing.amount
        existing.amount = amount
        existing.save(update_fields=["amount"])
        pc = existing
        old_val = {"amount": str(old_amount), "effective_from": effective_from.isoformat()}
        new_val = {"amount": str(amount), "effective_from": effective_from.isoformat()}
    else:
        pc = PriceChange.objects.create(
            subscription=sub,
            amount=amount,
            currency=sub.currency,
            effective_from=effective_from,
        )
        old_val = None
        new_val = {
            "subscription_id": sub.pk,
            "amount": str(amount),
            "effective_from": effective_from.isoformat(),
        }

    _emit_prices_changed(sub)
    _plan_audit(
        user,
        "price_change.created",
        "PriceChange",
        pc.pk,
        old_val,
        new_val,
        sub,
        f"Price changes from {effective_from.isoformat()}",
        amount=amount,
    )
    return pc, created


@transaction.atomic
def pause_subscription(user, pk: int) -> Subscription:
    sub = _lock_owned_subscription(user, pk)
    if sub.status == SubscriptionStatus.PAUSED:
        _invalid_status_change(sub, "pause")
    if sub.status not in (SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE):
        _invalid_status_change(sub, "pause")
    today = today_dhaka()
    old_status = sub.status
    sub.status = SubscriptionStatus.PAUSED
    sub.paused_on = today
    void_upcoming_untouched_charges(sub)
    sub.save(update_fields=["status", "paused_on"])
    _emit_status_changed(sub)
    _plan_audit(
        user,
        "plan.paused",
        "Subscription",
        sub.pk,
        {"status": old_status},
        {"status": sub.status},
        sub,
        "You paused the plan. No new charges until you resume.",
    )
    # TODO(notifications): notify members that the plan was paused.
    return sub


@transaction.atomic
def resume_subscription(user, pk: int) -> Subscription:
    sub = _lock_owned_subscription(user, pk)
    if sub.status != SubscriptionStatus.PAUSED:
        _invalid_status_change(sub, "resume")
    today = today_dhaka()
    old_status = sub.status
    sub.paused_on = None
    sub.billing_from = today
    sub.status = _status_for_trial_rule(sub)
    sub.save(update_fields=["status", "paused_on", "billing_from"])
    _emit_status_changed(sub)
    _plan_audit(
        user,
        "plan.resumed",
        "Subscription",
        sub.pk,
        {"status": old_status},
        {"status": sub.status},
        sub,
        "You resumed the plan.",
    )
    # TODO(notifications): notify members that the plan was resumed.
    return sub


@transaction.atomic
def cancel_subscription(user, pk: int) -> Subscription:
    sub = _lock_owned_subscription(user, pk)
    if sub.status == SubscriptionStatus.CANCELLED:
        _invalid_status_change(sub, "cancel")
    if sub.status not in (
        SubscriptionStatus.TRIAL,
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.PAUSED,
    ):
        _invalid_status_change(sub, "cancel")
    from core.schedule import next_due_date

    today = today_dhaka()
    old_status = sub.status
    sub.status = SubscriptionStatus.CANCELLED
    cancelled_on = next_due_date(_schedule_for(sub), today)
    sub.cancelled_on = cancelled_on
    if cancelled_on is not None:
        void_untouched_charges_on_or_after(sub, cancelled_on)
    sub.save(update_fields=["status", "cancelled_on"])
    _emit_status_changed(sub)
    _plan_audit(
        user,
        "plan.cancelled",
        "Subscription",
        sub.pk,
        {"status": old_status},
        {"status": sub.status},
        sub,
        "You cancelled the plan.",
    )
    # TODO(notifications): notify members that the plan was cancelled.
    return sub


@transaction.atomic
def renew_subscription(user, pk: int, *, end_date) -> Subscription:
    sub = _lock_owned_subscription(user, pk)
    if sub.renewal_type != RenewalType.FIXED_TERM:
        raise ValidationFailed(
            "Only fixed-term plans can be renewed.",
            code="not_fixed_term",
            fields={"renewal_type": ["Only fixed-term plans can be renewed."]},
        )
    if sub.status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED):
        _invalid_status_change(sub, "renew")
    today = today_dhaka()
    if end_date <= today:
        raise ValidationFailed(
            "End date must be after today.",
            fields={"end_date": ["End date must be after today."]},
        )
    if sub.end_date and end_date <= sub.end_date:
        raise ValidationFailed(
            "End date must be after the current end date.",
            fields={"end_date": ["End date must be after the current end date."]},
        )
    old_status = sub.status
    old_end = sub.end_date.isoformat() if sub.end_date else None
    sub.end_date = end_date
    sub.status = _status_for_trial_rule(sub)
    sub.save(update_fields=["end_date", "status"])
    _emit_status_changed(sub)
    _plan_audit(
        user,
        "plan.renewed",
        "Subscription",
        sub.pk,
        {"status": old_status, "end_date": old_end},
        {"status": sub.status, "end_date": sub.end_date.isoformat()},
        sub,
        f"You renewed the plan until {sub.end_date.isoformat()}",
    )
    # TODO(notifications): notify members that the plan was renewed.
    return sub


def create_exchange_rate(user, *, rate_date, usd_to_bdt: Decimal) -> ExchangeRate:
    return ExchangeRate.objects.create(
        user=user,
        rate_date=rate_date,
        usd_to_bdt=usd_to_bdt,
        source="manual",
    )
