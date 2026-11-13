from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.dates import today_dhaka
from core.exceptions import DomainError
from payments import services


def _domain_response(exc: DomainError):
    from core.exceptions import error_response

    return error_response(exc.code, exc.message, exc.fields, exc.status_code)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def payment_submit(request):
    data = request.data
    due_ids = data.get("due_ids") or []
    if not isinstance(due_ids, list):
        return _domain_response(
            DomainError("Invalid due list.", fields={"due_ids": ["Invalid due list."]})
        )
    try:
        due_ids = [int(x) for x in due_ids]
    except (TypeError, ValueError):
        return _domain_response(
            DomainError("Invalid due list.", fields={"due_ids": ["Invalid due list."]})
        )
    try:
        plan_id = int(data.get("plan_id"))
    except (TypeError, ValueError):
        return _domain_response(DomainError("Invalid plan.", fields={"plan_id": ["Invalid plan."]}))

    from decimal import Decimal

    amount = data.get("amount")
    parsed_amount = None
    if amount is not None and amount != "":
        try:
            parsed_amount = Decimal(str(amount))
        except Exception:
            return _domain_response(DomainError("Invalid amount.", fields={"amount": ["Invalid amount."]}))

    paid_on = None
    if raw_date := data.get("paid_on"):
        try:
            from datetime import date

            paid_on = date.fromisoformat(str(raw_date))
        except ValueError:
            return _domain_response(
                DomainError("Invalid date.", fields={"paid_on": ["Use YYYY-MM-DD."]})
            )

    today = today_dhaka()
    try:
        payment = services.submit_payment(
            request.user,
            plan_id=plan_id,
            due_ids=due_ids,
            method=data.get("method", ""),
            transaction_id=data.get("transaction_id", ""),
            amount=parsed_amount,
            paid_on=paid_on,
            today=today,
        )
    except DomainError as exc:
        return _domain_response(exc)
    return Response(
        {"payment_id": payment.pk, "message": services.submit_message(payment)},
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def payment_confirm(request, pk: int):
    try:
        body = services.confirm_payment(request.user, pk)
    except DomainError as exc:
        return _domain_response(exc)
    return Response(body)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def payment_reject(request, pk: int):
    try:
        body = services.reject_payment(request.user, pk, reason=request.data.get("reason", ""))
    except DomainError as exc:
        return _domain_response(exc)
    return Response(body)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def payment_reverse(request, pk: int):
    try:
        body = services.reverse_payment(request.user, pk)
    except DomainError as exc:
        return _domain_response(exc)
    return Response(body)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def due_mark_paid(request, pk: int):
    today = today_dhaka()
    raw_date = request.data.get("date")
    paid_on = None
    if raw_date:
        try:
            from datetime import date

            paid_on = date.fromisoformat(str(raw_date))
        except ValueError:
            return _domain_response(DomainError("Invalid date.", fields={"date": ["Use YYYY-MM-DD."]}))
    try:
        body = services.mark_due_paid(
            request.user,
            pk,
            paid_on=paid_on,
            method=request.data.get("method", ""),
            note=request.data.get("note", ""),
            today=today,
        )
    except DomainError as exc:
        return _domain_response(exc)
    return Response(body)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def payment_waive(request, pk: int):
    try:
        body = services.waive_payment(request.user, pk, note=request.data.get("note", ""))
    except DomainError as exc:
        return _domain_response(exc)
    return Response(body)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def due_waive(request, pk: int):
    try:
        body = services.waive_due(request.user, pk, note=request.data.get("note", ""))
    except DomainError as exc:
        return _domain_response(exc)
    return Response(body)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def due_set_due(request, pk: int):
    try:
        body = services.set_due_back(request.user, pk)
    except DomainError as exc:
        return _domain_response(exc)
    return Response(body)
