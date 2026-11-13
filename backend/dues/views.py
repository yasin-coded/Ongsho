from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.dates import today_dhaka
from core.exceptions import DomainError
from core.pagination import OngshoPageNumberPagination
from dues import selectors


def _domain_response(exc: DomainError):
    from core.exceptions import error_response

    return error_response(exc.code, exc.message, exc.fields, exc.status_code)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def due_list(request):
    try:
        params = selectors.parse_dues_list_params(request)
    except DomainError as exc:
        return _domain_response(exc)
    if plan_id := params.get("plan"):
        from plans.selectors import owned_subscription

        try:
            owned_subscription(request.user, plan_id)
        except DomainError as exc:
            return _domain_response(exc)
    try:
        qs = selectors.owner_dues_qs(request.user, params=params)
    except DomainError as exc:
        return _domain_response(exc)
    paginator = OngshoPageNumberPagination()
    page = paginator.paginate_queryset(qs, request, view=None)
    data = [selectors.due_list_row(d) for d in page]
    return paginator.get_paginated_response(data)
