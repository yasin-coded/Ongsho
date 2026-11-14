from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.dates import today_dhaka
from core.exceptions import DomainError
from reports import selectors
from reports import services as report_services


def _domain_response(exc: DomainError):
    from core.exceptions import error_response

    return error_response(exc.code, exc.message, exc.fields, exc.status_code)


def _pdf_response(pdf: bytes, number: str) -> HttpResponse:
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="ongsho-statement-{number}.pdf"'
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["X-Statement-Number"] = number
    return response


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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def owner_statement(request, pk: int):
    today = today_dhaka()
    try:
        pdf, stmt = report_services.issue_owner_statement(request.user, pk, request, today)
    except DomainError as exc:
        return _domain_response(exc)
    return _pdf_response(pdf, stmt.number)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def member_statement(request, pk: int):
    today = today_dhaka()
    try:
        pdf, stmt = report_services.issue_member_statement(request.user, pk, request, today)
    except DomainError as exc:
        return _domain_response(exc)
    return _pdf_response(pdf, stmt.number)
