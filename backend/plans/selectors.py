from datetime import timedelta
from decimal import Decimal

from django.db.models import DecimalField, Exists, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce

from catalog.selectors import available_service_names
from core.dates import today_dhaka
from core.exceptions import NotFound
from payments.models import Payment, ReviewStatus
from core.money import quantize_money, to_bdt
from core.schedule import first_bill_date, monthly_equivalent, next_due_date
from billing.selectors import schedule_for_subscription
from plans.models import ExchangeRate, PriceChange, Subscription, SubscriptionStatus


def owned_subscription(user, pk: int) -> Subscription:
    sub = (
        Subscription.objects.filter(owner=user, pk=pk)
        .select_related("service_name", "category", "owner")
        .first()
    )
    if sub is None:
        raise NotFound("Plan not found.")
    return sub


def owned_subscriptions(user, params: dict):
    qs = Subscription.objects.filter(owner=user).select_related("service_name", "category")
    search = (params.get("search") or "").strip()
    if search:
        qs = qs.filter(
            Q(plan_name__icontains=search)
            | Q(service_name__name__icontains=search)
            | Q(note__icontains=search)
        )
    if status := params.get("status"):
        qs = qs.filter(status=status)
    if category := params.get("category"):
        qs = qs.filter(category_id=category)
    if currency := params.get("currency"):
        qs = qs.filter(currency=currency)
    if plan_mode := params.get("plan_mode"):
        qs = qs.filter(plan_mode=plan_mode)
    if (rare := params.get("rarely_used")) is not None and rare != "":
        qs = qs.filter(rarely_used=rare)
    if params.get("needs_review"):
        pending_payment = Payment.objects.filter(
            shared_plan__subscription_id=OuterRef("pk"),
            review_status=ReviewStatus.PENDING,
        )
        qs = qs.filter(Exists(pending_payment))
    ordering = params.get("ordering") or "-id"
    qs = qs.order_by(ordering)

    today = today_dhaka()
    current_amount = Subquery(
        PriceChange.objects.filter(subscription_id=OuterRef("pk"), effective_from__lte=today)
        .order_by("-effective_from")
        .values("amount")[:1]
    )
    earliest_amount = Subquery(
        PriceChange.objects.filter(subscription_id=OuterRef("pk")).order_by("effective_from").values("amount")[:1]
    )
    latest_rate = Subquery(
        ExchangeRate.objects.filter(user_id=OuterRef("owner_id"), rate_date__lte=today)
        .order_by("-rate_date", "-id")
        .values("usd_to_bdt")[:1]
    )
    return qs.annotate(
        current_amount=Coalesce(
            current_amount,
            earliest_amount,
            output_field=DecimalField(max_digits=12, decimal_places=2),
        ),
        latest_usd_rate=latest_rate,
    )


def price_changes_for_subscription(subscription: Subscription):
    return PriceChange.objects.filter(subscription=subscription).order_by("-effective_from", "-id")


def current_amount_for_subscription(subscription: Subscription):
    today = today_dhaka()
    row = (
        PriceChange.objects.filter(subscription=subscription, effective_from__lte=today)
        .order_by("-effective_from")
        .first()
    )
    if row:
        return row.amount
    first = PriceChange.objects.filter(subscription=subscription).order_by("effective_from").first()
    return first.amount if first else None


def service_name_for_user(user, service_name_id: int):
    return available_service_names(user).filter(pk=service_name_id).select_related("category").first()


def exchange_rates_for_user(user):
    return ExchangeRate.objects.filter(user=user).order_by("-rate_date", "-id")


def _latest_rate(user, today):
    return (
        ExchangeRate.objects.filter(user=user, rate_date__lte=today)
        .order_by("-rate_date", "-id")
        .first()
    )


def display_next_renewal(sub: Subscription):
    if sub.status == SubscriptionStatus.TRIAL and sub.trial_end_date:
        return sub.trial_end_date.isoformat()
    if sub.status in (
        SubscriptionStatus.PAUSED,
        SubscriptionStatus.CANCELLED,
        SubscriptionStatus.EXPIRED,
    ):
        return None
    today = today_dhaka()
    schedule = schedule_for_subscription(sub)
    first = first_bill_date(schedule.start_date, schedule.trial_end_date)
    nxt = next_due_date(schedule, today)
    if nxt is None:
        return None
    if nxt == first and today >= first:
        follow = next_due_date(schedule, first + timedelta(days=1))
        if follow:
            return follow.isoformat()
    return nxt.isoformat()


def price_now_dict(sub: Subscription) -> dict | None:
    if hasattr(sub, "current_amount"):
        amount = sub.current_amount
    else:
        amount = current_amount_for_subscription(sub)
    if amount is None:
        return None
    rate = None
    amount_bdt = quantize_money(amount)
    if sub.currency == "USD":
        usd_rate = getattr(sub, "latest_usd_rate", None)
        if usd_rate is None:
            row = _latest_rate(sub.owner, today_dhaka())
            if row is None:
                return None
            usd_rate = row.usd_to_bdt
        rate = str(usd_rate)
        amount_bdt = to_bdt(amount, usd_rate)
    monthly_bdt = monthly_equivalent(amount_bdt, sub.cycle_unit, sub.cycle_count)
    return {
        "amount": str(quantize_money(amount)),
        "currency": sub.currency,
        "rate": rate,
        "amount_bdt": str(amount_bdt),
        "monthly_cost_bdt": str(monthly_bdt),
    }


def subscription_list_totals(user) -> dict:
    qs = owned_subscriptions(user, {}).filter(
        status__in=(SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL),
    )
    total = Decimal("0")
    count = 0
    for sub in qs:
        data = price_now_dict(sub)
        if data is None:
            continue
        count += 1
        total += Decimal(data["monthly_cost_bdt"])
    return {"count": count, "to_providers": str(quantize_money(total))}


def subscription_list_counts(user) -> dict[str, int]:
    base = Subscription.objects.filter(owner=user)
    pending_payment = Payment.objects.filter(
        shared_plan__subscription_id=OuterRef("pk"),
        review_status=ReviewStatus.PENDING,
    )
    return {
        "all": base.count(),
        "review": base.filter(Exists(pending_payment)).count(),
        "rarely": base.filter(rarely_used=True).count(),
    }
