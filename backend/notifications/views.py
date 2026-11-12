from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.exceptions import DomainError, ValidationFailed
from core.pagination import OngshoPageNumberPagination
from notifications import selectors, services


def _domain_response(exc: DomainError):
    from core.exceptions import error_response

    return error_response(exc.code, exc.message, exc.fields, exc.status_code)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def notification_list(request):
    filter_name = request.query_params.get("filter", "all")
    if filter_name not in selectors.LIST_FILTERS:
        return _domain_response(
            ValidationFailed(
                "Invalid filter.",
                fields={"filter": ["Must be one of: all, action, payments, plans, reminders."]},
            )
        )
    counts, unread = selectors.notification_counts(request.user)
    paginator = OngshoPageNumberPagination()

    if filter_name == "action":
        actionable = selectors.notifications_for_action_filter(request.user)
        page = paginator.paginate_queryset(actionable, request, view=None)
    else:
        qs = selectors.filter_queryset(request.user, filter_name)
        page = paginator.paginate_queryset(qs, request, view=None)

    data = selectors.serialize_page(list(page or []))
    extra = {"counts": counts, "unread": unread}
    return paginator.get_paginated_response(data, extra=extra)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def notification_mark_read(request, pk: int):
    try:
        note = services.mark_notification_read(request.user, pk)
    except DomainError as exc:
        return _domain_response(exc)
    resolved = selectors.resolve_for_notifications([note])
    return Response(selectors.notification_item_dict(note, resolved_value=resolved.get(note.pk)))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def notification_read_all(request):
    updated = services.mark_all_notifications_read(request.user)
    return Response({"updated": updated})
