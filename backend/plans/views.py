from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.exceptions import DomainError
from core.pagination import OngshoPageNumberPagination
from plans import selectors, services
from plans.serializers import ExchangeRateCreateSerializer, ExchangeRateSerializer


def _domain_response(exc: DomainError) -> Response:
    from core.exceptions import error_response

    return error_response(exc.code, exc.message, exc.fields, exc.status_code)


@api_view(["GET", "POST", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def exchange_rate_list_create(request):
    if request.method in ("PUT", "PATCH", "DELETE"):
        from core.exceptions import error_response

        return error_response("method_not_allowed", "Method not allowed.", {}, 405)
    if request.method == "GET":
        qs = selectors.exchange_rates_for_user(request.user)
        paginator = OngshoPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=None)
        serializer = ExchangeRateSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
    serializer = ExchangeRateCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    rate = services.create_exchange_rate(
        request.user,
        rate_date=serializer.validated_data["rate_date"],
        usd_to_bdt=serializer.validated_data["usd_to_bdt"],
    )
    return Response(ExchangeRateSerializer(rate).data, status=status.HTTP_201_CREATED)
