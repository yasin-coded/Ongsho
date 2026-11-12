from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from accounts.cookies import set_refresh_cookie
from accounts.serializers import user_public_dict
from core.dates import today_dhaka
from dues import selectors as dues_selectors
from core.exceptions import DomainError
from sharing import selectors, serializers as sharing_serializers, services
from sharing.models import SplitType

User = get_user_model()


def _domain_response(exc: DomainError):
    from core.exceptions import error_response

    return error_response(exc.code, exc.message, exc.fields, exc.status_code)


def _method_not_allowed():
    from core.exceptions import error_response

    return error_response("method_not_allowed", "Method not allowed.", {}, 405)


@api_view(["GET", "PATCH", "PUT", "DELETE"])
@permission_classes([IsAuthenticated])
def shared_plan_detail(request, pk: int):
    if request.method in ("PUT", "DELETE"):
        return _method_not_allowed()
    if request.method == "GET":
        shared = selectors.shared_plan_for_owner(request.user, pk)
        return Response(
            {
                "plan_id": shared.subscription_id,
                "split_type": shared.split_type,
                "seats": shared.seats,
                "member_count": selectors.member_count_active(shared),
                "pending_invite_count": selectors.pending_invite_count(shared),
            }
        )
    seats = request.data.get("seats")
    try:
        seats = int(seats)
    except (TypeError, ValueError):
        return _domain_response(
            DomainError("Invalid seats.", code="validation_failed", fields={"seats": ["Enter a valid number."]})
        )
    try:
        shared = services.update_seats(request.user, pk, seats=seats)
    except DomainError as exc:
        return _domain_response(exc)
    return Response(
        {
            "plan_id": shared.subscription_id,
            "split_type": shared.split_type,
            "seats": shared.seats,
            "member_count": selectors.member_count_active(shared),
            "pending_invite_count": selectors.pending_invite_count(shared),
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def subscription_share(request, pk: int):
    split_type = request.data.get("split_type")
    seats = request.data.get("seats")
    try:
        seats = int(seats)
    except (TypeError, ValueError):
        return _domain_response(
            DomainError("Invalid seats.", code="validation_failed", fields={"seats": ["Enter a valid number."]})
        )
    try:
        shared = services.share_plan(
            request.user, pk, split_type=split_type, seats=seats, today=today_dhaka()
        )
    except DomainError as exc:
        return _domain_response(exc)
    return Response(
        {
            "plan_id": shared.subscription_id,
            "split_type": shared.split_type,
            "seats": shared.seats,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def shared_plan_invites(request, pk: int):
    shared = selectors.shared_plan_for_owner(request.user, pk)
    if request.method == "GET":
        invites = (
            shared.invites.select_related("invited_by", "accepted_by")
            .order_by("-created_at", "-id")
        )
        return Response([sharing_serializers.invite_row(i) for i in invites])
    email = request.data.get("email", "")
    try:
        invite, raw = services.create_invite(request.user, pk, email=email, today=today_dhaka())
    except DomainError as exc:
        return _domain_response(exc)
    data = sharing_serializers.invite_row(invite)
    data["link"] = services._invite_link(raw)
    return Response(data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def invite_cancel(request, pk: int):
    try:
        invite = services.cancel_invite(request.user, pk)
    except DomainError as exc:
        return _domain_response(exc)
    return Response(sharing_serializers.invite_row(invite))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def invite_new_link(request, pk: int):
    try:
        invite, raw = services.new_invite_link(request.user, pk, today=today_dhaka())
    except DomainError as exc:
        return _domain_response(exc)
    data = sharing_serializers.invite_row(invite)
    data["link"] = services._invite_link(raw)
    return Response(data)


@api_view(["GET"])
@permission_classes([AllowAny])
def invite_public(request, token: str):
    try:
        invite = selectors.invite_by_token(token)
    except DomainError as exc:
        return _domain_response(exc)
    shared = invite.shared_plan
    sub = shared.subscription
    per = services._per_seat_bdt(shared)
    return Response(
        {
            "id": invite.pk,
            "email": invite.email,
            "status": selectors.invite_display_status(invite),
            "expires_on": invite.expires_on,
            "expired": invite.expires_on <= timezone.now(),
            "account_exists": User.objects.filter(email__iexact=invite.email).exists(),
            "plan_id": sub.pk,
            "plan_name": sub.plan_name,
            "seats": shared.seats,
            "from": services._first_name(invite.invited_by),
            "share": str(per) if per is not None else None,
            "cycle": {"unit": sub.cycle_unit, "count": sub.cycle_count},
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def invite_accept_token(request, token: str):
    try:
        result = services.accept_invite(request.user, token=token, today=today_dhaka())
    except DomainError as exc:
        return _domain_response(exc)
    return Response(result)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def invite_decline_token(request, token: str):
    try:
        result = services.decline_invite(request.user, token=token)
    except DomainError as exc:
        return _domain_response(exc)
    return Response(result)


@api_view(["POST"])
@permission_classes([AllowAny])
def invite_signup(request, token: str):
    try:
        access, refresh, user, plan_id = services.signup_via_invite(
            token=token,
            name=request.data.get("name", ""),
            password=request.data.get("password", ""),
            today=today_dhaka(),
        )
    except DomainError as exc:
        return _domain_response(exc)
    response = Response(
        {"access": access, "user": user_public_dict(user), "plan_id": plan_id},
        status=status.HTTP_201_CREATED,
    )
    set_refresh_cookie(response, refresh)
    return response


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_pending_invites(request):
    invites = selectors.invite_for_user_pending(request.user)
    return Response([sharing_serializers.me_invite_row(i) for i in invites])


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def my_invite_accept(request, pk: int):
    if not selectors.invite_for_recipient(request.user, pk):
        from core.exceptions import NotFound

        return _domain_response(NotFound("Not found."))
    try:
        result = services.accept_invite(request.user, invite_id=pk, today=today_dhaka())
    except DomainError as exc:
        return _domain_response(exc)
    return Response(result)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def my_invite_decline(request, pk: int):
    if not selectors.invite_for_recipient(request.user, pk):
        from core.exceptions import NotFound

        return _domain_response(NotFound("Not found."))
    try:
        result = services.decline_invite(request.user, invite_id=pk)
    except DomainError as exc:
        return _domain_response(exc)
    return Response(result)


@api_view(["GET", "PATCH", "POST", "DELETE"])
@permission_classes([IsAuthenticated])
def shared_plan_members(request, pk: int):
    if request.method != "GET":
        return _method_not_allowed()
    shared = selectors.shared_plan_for_owner(request.user, pk)
    include_left = request.query_params.get("include") == "left"
    members = list(selectors.members_queryset(shared, include_left=include_left))
    today = today_dhaka()
    ctx = dues_selectors.prefetch_member_payment_ctx(shared, members, today)
    return Response([sharing_serializers.member_row(m, due_ctx=ctx.get(m.pk)) for m in members])


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def member_balance(request, pk: int):
    try:
        member = selectors.member_for_owner(request.user, pk)
    except DomainError as exc:
        return _domain_response(exc)
    return Response(dues_selectors.member_balance(member))


@api_view(["GET", "PATCH", "POST"])
@permission_classes([IsAuthenticated])
def member_detail(request, pk: int):
    if request.method != "GET":
        return _method_not_allowed()
    member = selectors.member_for_owner(request.user, pk)
    today = today_dhaka()
    ctx = dues_selectors.prefetch_member_payment_ctx(member.shared_plan, [member], today)
    rows = dues_selectors.member_history_rows(member)
    return Response(
        sharing_serializers.member_detail_row(member, due_ctx=ctx.get(member.pk), rows=rows)
    )


@api_view(["POST", "DELETE"])
@permission_classes([IsAuthenticated])
def leave_request(request, pk: int):
    try:
        if request.method == "POST":
            services.request_leave(request.user, pk, today=today_dhaka())
            return Response({"message": "Leave request sent."})
        services.cancel_leave_request(request.user, pk)
        return Response({"message": "Leave request cancelled."})
    except DomainError as exc:
        return _domain_response(exc)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def owner_leave_decision(request, pk: int):
    approve = request.data.get("approve")
    leave_date = request.data.get("leave_date")
    unpaid = request.data.get("unpaid")
    from datetime import date

    parsed_date = None
    if leave_date:
        try:
            parsed_date = date.fromisoformat(str(leave_date))
        except ValueError:
            return _domain_response(
                DomainError(
                    "Invalid leave date.",
                    fields={"leave_date": ["Enter a valid date."]},
                )
            )
    try:
        services.owner_leave_decision(
            request.user,
            pk,
            today=today_dhaka(),
            approve=bool(approve),
            leave_date=parsed_date,
            unpaid=unpaid,
        )
    except DomainError as exc:
        return _domain_response(exc)
    return Response({"message": "OK"})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def member_replace(request, pk: int):
    try:
        invite, raw = services.replace_member(
            request.user, pk, email=request.data.get("email", ""), today=today_dhaka()
        )
    except DomainError as exc:
        return _domain_response(exc)
    data = sharing_serializers.invite_row(invite)
    data["link"] = services._invite_link(raw)
    return Response(data, status=status.HTTP_201_CREATED)


@api_view(["PUT", "POST", "GET", "DELETE"])
@permission_classes([IsAuthenticated])
def shared_plan_split(request, pk: int):
    if request.method != "PUT":
        return _method_not_allowed()
    split_type = request.data.get("split_type")
    shares = request.data.get("shares")
    try:
        shared = services.update_split(
            request.user, pk, split_type=split_type, shares=shares, today=today_dhaka()
        )
    except DomainError as exc:
        return _domain_response(exc)
    return Response({"split_type": shared.split_type})
