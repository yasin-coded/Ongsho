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
def me_shared_plan_list(request):
    today = today_dhaka()
    plan_filter = request.query_params.get("filter", "all")
    try:
        qs = list(selectors.me_shared_plans_qs(request.user, plan_filter=plan_filter, today=today))
    except DomainError as exc:
        return _domain_response(exc)
    memberships = list(qs)
    counts = selectors.me_shared_plan_counts(memberships, today)
    totals = selectors.me_shared_plan_totals(memberships, today)
    if plan_filter != "all":
        memberships = selectors.filter_memberships_by_status(memberships, plan_filter, today)
    paginator = OngshoPageNumberPagination()
    page = paginator.paginate_queryset(memberships, request, view=None)
    data = [selectors.me_shared_plan_item(m, today) for m in page]
    return paginator.get_paginated_response(data, extra={"counts": counts, "totals": totals})


@api_view(["GET", "POST", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def me_shared_plan_detail(request, pk: int):
    if request.method != "GET":
        from core.exceptions import error_response

        return error_response("method_not_allowed", "Method not allowed.", {}, 405)
    today = today_dhaka()
    try:
        member = selectors.active_membership(request.user, pk)
    except DomainError as exc:
        return _domain_response(exc)
    return Response(selectors.me_shared_plan_detail(member, today))
