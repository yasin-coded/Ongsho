from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied
from django.http import Http404
from rest_framework import exceptions as drf_exc
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class DomainError(Exception):
    """Base for service-layer errors mapped by the global handler."""

    code: str = "error"
    status_code: int = 400

    def __init__(
        self,
        message: str,
        *,
        fields: dict[str, list[str]] | None = None,
        code: str | None = None,
        status_code: int | None = None,
    ):
        self.message = message
        self.fields = fields or {}
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class ValidationFailed(DomainError):
    code = "validation_failed"
    status_code = 400


class NotFound(DomainError):
    code = "not_found"
    status_code = 404


class ConflictError(DomainError):
    code = "conflict"
    status_code = 409


class Forbidden(DomainError):
    code = "forbidden"
    status_code = 403


class Unauthorized(DomainError):
    code = "unauthorized"
    status_code = 401


class Locked(DomainError):
    code = "locked"
    status_code = 429

    def __init__(
        self,
        message: str,
        *,
        retry_after: int,
        fields: dict[str, list[str]] | None = None,
        code: str | None = None,
        status_code: int | None = None,
    ):
        super().__init__(message, fields=fields, code=code, status_code=status_code)
        self.retry_after = retry_after


def _stringify_detail(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, dict):
        msgs: list[str] = []
        for nested in value.values():
            msgs.extend(_stringify_detail(nested))
        return msgs
    return [str(value)]


def _detail_to_fields(detail: Any) -> tuple[str, dict[str, list[str]]]:
    if isinstance(detail, dict):
        fields = {key: _stringify_detail(val) for key, val in detail.items()}
        first = next(iter(fields.values()), ["Validation failed."])
        return first[0], fields
    if isinstance(detail, list):
        return str(detail[0]) if detail else "Validation failed.", {}
    return str(detail), {}


def error_response(
    code: str,
    message: str,
    fields: dict[str, list[str]] | None,
    status: int,
    *,
    retry_after: int | None = None,
) -> Response:
    response = Response(
        {"error": {"code": code, "message": message, "fields": fields or {}}},
        status=status,
    )
    if retry_after is not None:
        response["Retry-After"] = str(int(retry_after))
    return response


def domain_error_response(exc: DomainError) -> Response:
    return error_response(
        exc.code,
        exc.message,
        exc.fields,
        exc.status_code,
        retry_after=getattr(exc, "retry_after", None),
    )


def ongsho_exception_handler(exc, context):
    if isinstance(exc, DomainError):
        return domain_error_response(exc)

    if isinstance(exc, Http404):
        return error_response("not_found", "Not found.", {}, 404)

    if isinstance(exc, PermissionDenied):
        return error_response("forbidden", "Forbidden.", {}, 403)

    response = drf_exception_handler(exc, context)

    if isinstance(exc, drf_exc.ValidationError):
        message, fields = _detail_to_fields(exc.detail)
        code = getattr(exc, "default_code", "validation_failed")
        if hasattr(code, "value"):
            code = code.value
        return error_response(str(code), message, fields, 400)

    if isinstance(exc, drf_exc.AuthenticationFailed):
        code = getattr(exc, "default_code", "authentication_failed")
        if hasattr(code, "value"):
            code = code.value
        message = _detail_to_fields(exc.detail)[0]
        return error_response(str(code), message, {}, 401)

    if isinstance(exc, drf_exc.NotAuthenticated):
        return error_response("not_authenticated", "Authentication credentials were not provided.", {}, 401)

    if isinstance(exc, drf_exc.PermissionDenied):
        return error_response("forbidden", _detail_to_fields(exc.detail)[0], {}, 403)

    if isinstance(exc, drf_exc.NotFound):
        return error_response("not_found", _detail_to_fields(exc.detail)[0], {}, 404)

    if isinstance(exc, drf_exc.MethodNotAllowed):
        return error_response("method_not_allowed", _detail_to_fields(exc.detail)[0], {}, 405)

    if isinstance(exc, drf_exc.Throttled):
        retry = exc.wait
        headers = {"Retry-After": str(int(retry))} if retry is not None else {}
        resp = error_response("throttled", _detail_to_fields(exc.detail)[0], {}, 429)
        for key, value in headers.items():
            resp[key] = value
        return resp

    if response is not None:
        message, fields = _detail_to_fields(response.data)
        status = response.status_code
        if status == 401:
            code = "not_authenticated"
        elif status == 403:
            code = "forbidden"
        elif status == 404:
            code = "not_found"
        elif status == 409:
            code = "conflict"
        else:
            code = "error"
        return error_response(code, message, fields, status)

    return error_response(
        "server_error",
        "Something went wrong. Please try again later.",
        {},
        500,
    )
