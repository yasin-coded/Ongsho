from datetime import date

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from billing import selectors, services
from billing.models import ChargeStatus
from billing.serializers import ChargeSerializer
from core.dates import today_dhaka
from core.exceptions import DomainError, ValidationFailed
from core.pagination import OngshoPageNumberPagination


def _domain_response(exc: DomainError) -> Response:
    from core.exceptions import error_response

    return error_response(exc.code, exc.message, exc.fields, exc.status_code)


def _parse_month(raw: str | None) -> date:
    if not raw:
        today = today_dhaka()
        return date(today.year, today.month, 1)
    try:
        parts = raw.split("-")
        if len(parts) != 2:
            raise ValueError
        year, month = int(parts[0]), int(parts[1])
        return date(year, month, 1)
    except (ValueError, TypeError):
        raise ValidationFailed("Invalid month.", fields={"month": ["Use YYYY-MM."]})


def _charge_list_params(request) -> dict:
    params: dict = {}
    plan_raw = request.query_params.get("plan")
    if plan_raw not in (None, ""):
        try:
            params["plan"] = int(plan_raw)
        except ValueError:
            raise ValidationFailed("Invalid plan.", fields={"plan": ["Invalid plan id."]})
    status_raw = request.query_params.get("status")
    if status_raw not in (None, ""):
        allowed = {c.value for c in ChargeStatus}
        if status_raw not in allowed:
            raise ValidationFailed("Invalid status.", fields={"status": ["Invalid status."]})
        params["status"] = status_raw
    month_raw = request.query_params.get("month")
    if month_raw not in (None, ""):
        try:
            parts = month_raw.split("-")
            year, month = int(parts[0]), int(parts[1])
            params["month"] = date(year, month, 1)
        except (ValueError, IndexError):
            raise ValidationFailed("Invalid month.", fields={"month": ["Use YYYY-MM."]})
    return params


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def charge_list(request):
    try:
        params = _charge_list_params(request)
    except DomainError as exc:
        return _domain_response(exc)
    qs = selectors.owner_charges_qs(request.user, params=params)
    paginator = OngshoPageNumberPagination()
    page = paginator.paginate_queryset(qs, request, view=None)
    return paginator.get_paginated_response(ChargeSerializer(page, many=True).data)


@api_view(["POST", "GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def charge_generate(request):
    if request.method != "POST":
        from core.exceptions import error_response

        return error_response("method_not_allowed", "Method not allowed.", {}, 405)
    counts = services.generate_charges_for_owner(request.user, today_dhaka())
    return Response({"plans": counts["plans"], "created": counts["created"]})


@api_view(["PATCH", "GET", "POST", "PUT", "DELETE"])
@permission_classes([IsAuthenticated])
def charge_rate(request, pk):
    if request.method != "PATCH":
        from core.exceptions import error_response

        return error_response("method_not_allowed", "Method not allowed.", {}, 405)
    rate = request.data.get("rate")
    if rate is None:
        return _domain_response(
            ValidationFailed("This field is required.", fields={"rate": ["This field is required."]})
        )
    try:
        charge = services.correct_rate(request.user, pk, rate, today_dhaka())
    except DomainError as exc:
        return _domain_response(exc)
    row = selectors.owner_charges_qs(request.user, params={}).filter(pk=charge.pk).first()
    return Response(ChargeSerializer(row).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def calendar_view(request):
    try:
        month_start = _parse_month(request.query_params.get("month"))
    except DomainError as exc:
        return _domain_response(exc)
    today = today_dhaka()
    events = selectors.calendar_events(request.user, today=today, month_start=month_start)
    next7_end = today + __import__("datetime").timedelta(days=6)
    next7 = [e for e in events if today <= date.fromisoformat(e["date"]) <= next7_end]
    month_events = [
        e
        for e in events
        if date.fromisoformat(e["date"]).year == month_start.year
        and date.fromisoformat(e["date"]).month == month_start.month
    ]
    return Response({"events": month_events, "next7": next7})
