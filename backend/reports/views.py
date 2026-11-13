from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.dates import today_dhaka
from core.exceptions import DomainError
from reports import selectors


def _domain_response(exc: DomainError):
    from core.exceptions import error_response

    return error_response(exc.code, exc.message, exc.fields, exc.status_code)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_summary(request):
    today = today_dhaka()
    try:
        month = selectors.parse_month_param(request, today)
    except DomainError as exc:
        return _domain_response(exc)
    return Response(selectors.dashboard_summary(request.user, month=month, today=today))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_forecast(request):
    today = today_dhaka()
    try:
        months = selectors.parse_forecast_months(request)
    except DomainError as exc:
        return _domain_response(exc)
    return Response(selectors.dashboard_forecast(request.user, months=months, today=today))
