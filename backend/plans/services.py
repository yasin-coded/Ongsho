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
    status = (
        SubscriptionStatus.TRIAL
        if trial_end and today <= trial_end
        else SubscriptionStatus.ACTIVE
    )
    start_date = validated["start_date"]
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
        anchor_day=start_date.day,
        start_date=start_date,
        trial_end_date=trial_end,
        renewal_type=validated["renewal_type"],
        end_date=validated.get("end_date"),
        status=status,
        recommended_method=validated["recommended_method"],
        rarely_used=validated.get("rarely_used", False),
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
    audit_services.log(
        user,
        "plan.created",
        "Subscription",
        sub.pk,
        None,
        {"id": sub.pk, "plan_name": sub.plan_name, "currency": sub.currency},
    )
    return sub, amount_bdt_preview


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
    audit_services.log(user, "plan.updated", "Subscription", sub.pk, old_snapshot, new_snapshot)
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
        audit_services.log(user, "plan.archived", "Subscription", entity_id, snapshot, None)
    else:
        sub.delete()
        audit_services.log(user, "plan.deleted", "Subscription", entity_id, snapshot, None)


@transaction.atomic
def add_price_change(user, pk: int, *, amount: Decimal, effective_from) -> PriceChange:
    sub = owned_subscription(user, pk)
    if effective_from < sub.start_date:
        raise ValidationFailed(
            "Effective date cannot be before the plan start date.",
            fields={"effective_from": ["Effective date cannot be before the plan start date."]},
        )
    amount = quantize_money(amount)
    if PriceChange.objects.filter(subscription=sub, effective_from=effective_from).exists():
        raise ConflictError(
            "A price change already exists for this date.",
            code="price_change_exists",
        )
    pc = PriceChange.objects.create(
        subscription=sub,
        amount=amount,
        currency=sub.currency,
        effective_from=effective_from,
    )
    audit_services.log(
        user,
        "price_change.created",
        "PriceChange",
        pc.pk,
        None,
        {"subscription_id": sub.pk, "amount": str(amount), "effective_from": effective_from.isoformat()},
    )
    return pc


def create_exchange_rate(user, *, rate_date, usd_to_bdt: Decimal) -> ExchangeRate:
    return ExchangeRate.objects.create(
        user=user,
        rate_date=rate_date,
        usd_to_bdt=usd_to_bdt,
        source="manual",
    )
