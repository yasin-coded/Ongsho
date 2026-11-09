from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.exceptions import DomainError, error_response
from plans import selectors, services
from plans.subscription_serializers import SubscriptionDetailSerializer, SubscriptionRenewSerializer


def _domain_response(exc: DomainError) -> Response:
    return error_response(exc.code, exc.message, exc.fields, exc.status_code)


def _method_not_allowed() -> Response:
    return error_response("method_not_allowed", "Method not allowed.", {}, 405)


def _status_post(request, pk, handler, *, with_body: bool = False):
    if request.method != "POST":
        return _method_not_allowed()
    if with_body:
        serializer = SubscriptionRenewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        kwargs = {"end_date": serializer.validated_data["end_date"]}
    else:
        kwargs = {}
    try:
        sub = handler(request.user, pk, **kwargs) if with_body else handler(request.user, pk)
    except DomainError as exc:
        return _domain_response(exc)
    sub = selectors.owned_subscription(request.user, sub.pk)
    return Response(SubscriptionDetailSerializer(sub).data)


@api_view(["POST", "GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def subscription_pause(request, pk):
    return _status_post(request, pk, services.pause_subscription)


@api_view(["POST", "GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def subscription_resume(request, pk):
    return _status_post(request, pk, services.resume_subscription)


@api_view(["POST", "GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def subscription_cancel(request, pk):
    return _status_post(request, pk, services.cancel_subscription)


@api_view(["POST", "GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def subscription_renew(request, pk):
    return _status_post(request, pk, services.renew_subscription, with_body=True)
