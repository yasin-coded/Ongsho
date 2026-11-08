from django.db.models import DecimalField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce

from catalog.selectors import available_service_names
from core.dates import today_dhaka
from core.exceptions import NotFound
from plans.models import ExchangeRate, PriceChange, Subscription


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
    return qs.annotate(
        current_amount=Coalesce(
            current_amount,
            earliest_amount,
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
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
