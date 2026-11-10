from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.exceptions import DomainError, ValidationFailed
from core.pagination import OngshoPageNumberPagination
from plans import selectors, services
from plans.subscription_serializers import (
    LOCKED_PATCH_FIELDS,
    PriceChangeCreateSerializer,
    PriceChangeSerializer,
    SubscriptionCreateSerializer,
    SubscriptionDeleteSerializer,
    SubscriptionDetailSerializer,
    SubscriptionListSerializer,
    SubscriptionPatchSerializer,
)

ORDERING_WHITELIST = frozenset(
    {"plan_name", "-plan_name", "start_date", "-start_date", "status", "-status", "id", "-id"}
)


def _domain_response(exc: DomainError) -> Response:
    from core.exceptions import error_response

    return error_response(exc.code, exc.message, exc.fields, exc.status_code)


def _list_params(request) -> dict:
    ordering = request.query_params.get("ordering", "-id")
    if ordering not in ORDERING_WHITELIST:
        raise ValidationFailed(
            "Invalid ordering.",
            fields={"ordering": ["Invalid ordering."]},
        )
    rarely_raw = request.query_params.get("rarely_used")
    rarely = None
    if rarely_raw is not None and rarely_raw != "":
        if rarely_raw.lower() not in ("true", "false"):
            raise ValidationFailed(
                "Invalid value.",
                fields={"rarely_used": ["Must be true or false."]},
            )
        rarely = rarely_raw.lower() == "true"
    needs_review_raw = request.query_params.get("needs_review")
    needs_review = None
    if needs_review_raw is not None and needs_review_raw != "":
        if needs_review_raw.lower() not in ("true", "false"):
            raise ValidationFailed(
                "Invalid value.",
                fields={"needs_review": ["Must be true or false."]},
            )
        needs_review = needs_review_raw.lower() == "true"
    status_val = request.query_params.get("status") or None
    if status_val is not None and status_val != "":
        from plans.models import SubscriptionStatus

        if status_val not in {c.value for c in SubscriptionStatus}:
            raise ValidationFailed("Invalid value.", fields={"status": ["Invalid status."]})
    currency = request.query_params.get("currency") or None
    if currency:
        from core.choices import Currency

        if currency not in {c.value for c in Currency}:
            raise ValidationFailed("Invalid value.", fields={"currency": ["Invalid currency."]})
    plan_mode = request.query_params.get("plan_mode") or None
    if plan_mode:
        from plans.models import PlanMode

        if plan_mode not in {c.value for c in PlanMode}:
            raise ValidationFailed("Invalid value.", fields={"plan_mode": ["Invalid plan mode."]})
    category = request.query_params.get("category")
    cat_id = None
    if category is not None and category != "":
        try:
            cat_id = int(category)
        except ValueError:
            raise ValidationFailed("Invalid value.", fields={"category": ["Invalid category id."]})
    return {
        "search": request.query_params.get("search", ""),
        "status": status_val or None,
        "category": cat_id,
        "currency": currency or None,
        "plan_mode": plan_mode or None,
        "rarely_used": rarely,
        "needs_review": needs_review,
        "ordering": ordering,
    }


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def subscription_list_create(request):
    if request.method == "GET":
        try:
            params = _list_params(request)
        except DomainError as exc:
            return _domain_response(exc)
        qs = selectors.owned_subscriptions(request.user, params)
        counts = selectors.subscription_list_counts(request.user)
        paginator = OngshoPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=None)
        data = SubscriptionListSerializer(page, many=True).data
        return paginator.get_paginated_response(data, extra={"counts": counts})
    serializer = SubscriptionCreateSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    try:
        sub, preview = services.create_subscription(request.user, serializer.validated_data)
    except DomainError as exc:
        return _domain_response(exc)
    sub = selectors.owned_subscription(request.user, sub.pk)
    out = SubscriptionDetailSerializer(sub).data
    if preview is not None:
        out["amount_bdt_preview"] = preview
    return Response(out, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "PUT", "DELETE"])
@permission_classes([IsAuthenticated])
def subscription_detail(request, pk):
    if request.method == "PUT":
        from core.exceptions import error_response

        return error_response("method_not_allowed", "Method not allowed.", {}, 405)
    if request.method == "GET":
        try:
            sub = selectors.owned_subscription(request.user, pk)
        except DomainError as exc:
            return _domain_response(exc)
        return Response(SubscriptionDetailSerializer(sub).data)
    if request.method == "PATCH":
        if "plan_mode" in request.data:
            return _domain_response(
                ValidationFailed(
                    "Plan mode cannot be changed after creation.",
                    code="plan_mode_locked",
                    fields={"plan_mode": ["Plan mode cannot be changed after creation."]},
                )
            )
        blocked = [f for f in LOCKED_PATCH_FIELDS if f in request.data]
        if blocked:
            return _domain_response(
                ValidationFailed(
                    "These fields cannot be changed.",
                    code="field_not_editable",
                    fields={f: ["This field cannot be changed."] for f in blocked},
                )
            )
        try:
            sub = selectors.owned_subscription(request.user, pk)
        except DomainError as exc:
            return _domain_response(exc)
        serializer = SubscriptionPatchSerializer(
            data=request.data,
            partial=True,
            context={"request": request, "subscription": sub},
        )
        serializer.is_valid(raise_exception=True)
        try:
            sub = services.update_subscription(request.user, pk, serializer.validated_data)
        except DomainError as exc:
            return _domain_response(exc)
        sub = selectors.owned_subscription(request.user, sub.pk)
        return Response(SubscriptionDetailSerializer(sub).data)
    serializer = SubscriptionDeleteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        services.delete_subscription(request.user, pk, serializer.validated_data["password"])
    except DomainError as exc:
        return _domain_response(exc)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET", "POST", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def price_change_list_create(request, pk):
    if request.method in ("PUT", "PATCH", "DELETE"):
        from core.exceptions import error_response

        return error_response("method_not_allowed", "Method not allowed.", {}, 405)
    try:
        sub = selectors.owned_subscription(request.user, pk)
    except DomainError as exc:
        return _domain_response(exc)
    if request.method == "GET":
        rows = selectors.price_changes_for_subscription(sub)
        return Response(PriceChangeSerializer(rows, many=True).data)
    serializer = PriceChangeCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        pc, created = services.add_price_change(
            request.user,
            pk,
            amount=serializer.validated_data["amount"],
            effective_from=serializer.validated_data["effective_from"],
            exchange_rate=serializer.validated_data.get("exchange_rate"),
        )
    except DomainError as exc:
        return _domain_response(exc)
    code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return Response(PriceChangeSerializer(pc).data, status=code)
