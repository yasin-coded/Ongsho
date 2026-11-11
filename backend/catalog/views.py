from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from catalog import selectors, services
from catalog.serializers import (
    CategoryCreateSerializer,
    CategorySerializer,
    ServiceNameCreateSerializer,
    ServiceNameSerializer,
)
from core.exceptions import DomainError


def _domain_response(exc: DomainError) -> Response:
    from core.exceptions import error_response

    return error_response(exc.code, exc.message, exc.fields, exc.status_code)


@api_view(["GET", "POST", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def category_list_create(request):
    if request.method in ("PUT", "PATCH", "DELETE"):
        from core.exceptions import error_response

        return error_response("method_not_allowed", "Method not allowed.", {}, 405)
    if request.method == "GET":
        categories = selectors.available_categories(request.user)
        return Response(CategorySerializer(categories, many=True).data)
    serializer = CategoryCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        category = services.create_category(request.user, serializer.validated_data["name"])
    except DomainError as exc:
        return _domain_response(exc)
    return Response(CategorySerializer(category).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "POST", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def service_name_list_create(request):
    if request.method in ("PUT", "PATCH", "DELETE"):
        from core.exceptions import error_response

        return error_response("method_not_allowed", "Method not allowed.", {}, 405)
    if request.method == "GET":
        category_id = request.query_params.get("category")
        parsed = None
        if category_id is not None and category_id != "":
            try:
                parsed = int(category_id)
            except ValueError:
                parsed = -1
        names = selectors.available_service_names(request.user, category_id=parsed)
        return Response(ServiceNameSerializer(names, many=True).data)
    serializer = ServiceNameCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        row = services.create_service_name(
            request.user,
            serializer.validated_data["name"],
            serializer.validated_data["category"],
        )
    except DomainError as exc:
        return _domain_response(exc)
    row = selectors.available_service_names(request.user).filter(pk=row.pk).first()
    return Response(ServiceNameSerializer(row).data, status=status.HTTP_201_CREATED)


@api_view(["DELETE", "GET", "POST", "PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def category_detail(request, pk):
    if request.method != "DELETE":
        from core.exceptions import error_response

        return error_response("method_not_allowed", "Method not allowed.", {}, 405)
    try:
        services.delete_category(request.user, pk)
    except DomainError as exc:
        return _domain_response(exc)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["DELETE", "GET", "POST", "PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def service_name_detail(request, pk):
    if request.method != "DELETE":
        from core.exceptions import error_response

        return error_response("method_not_allowed", "Method not allowed.", {}, 405)
    try:
        services.delete_service_name(request.user, pk)
    except DomainError as exc:
        return _domain_response(exc)
    return Response(status=status.HTTP_204_NO_CONTENT)
