"""Write routes for permission / hostile-input matrices (paired with GET rows in test_permissions_matrix)."""

from __future__ import annotations

from dataclasses import dataclass

from dues.models import DueStatus
from payments.models import ReviewStatus
from tests.test_payments import _submit
from tests.test_subscriptions import WORLD_PASS, client_for

Role = str  # anon | owner | member | outsider


@dataclass(frozen=True)
class WriteEndpoint:
    method: str
    path_template: str
    role: Role
    hostile_reject: bool = True


WRITE_ENDPOINT_MATRIX: tuple[WriteEndpoint, ...] = (
    # Auth (public POST)
    WriteEndpoint("POST", "/api/auth/register/", "anon"),
    WriteEndpoint("POST", "/api/auth/verify-email/", "anon"),
    WriteEndpoint("POST", "/api/auth/resend-verification/", "anon", hostile_reject=False),
    WriteEndpoint("POST", "/api/auth/login/", "anon"),
    WriteEndpoint("POST", "/api/auth/refresh/", "anon"),
    # logout always returns 204 when the app header is present (body ignored)
    WriteEndpoint("POST", "/api/auth/password-reset/", "anon", hostile_reject=False),
    WriteEndpoint("POST", "/api/auth/password-reset/confirm/", "anon"),
    # Me
    WriteEndpoint("PATCH", "/api/me/", "owner", hostile_reject=False),
    WriteEndpoint("PUT", "/api/me/", "owner", hostile_reject=False),
    WriteEndpoint("DELETE", "/api/me/", "owner"),
    WriteEndpoint("POST", "/api/me/password/", "owner"),
    WriteEndpoint("POST", "/api/me/email/", "owner"),
    WriteEndpoint("DELETE", "/api/me/email/", "owner", hostile_reject=False),
    WriteEndpoint("POST", "/api/me/email/verify/", "owner"),
    WriteEndpoint("POST", "/api/me/email/resend/", "owner"),
    WriteEndpoint("POST", "/api/me/close/", "owner"),
    WriteEndpoint("PATCH", "/api/reminders/settings/", "owner", hostile_reject=False),
    # Catalog
    WriteEndpoint("POST", "/api/categories/", "outsider"),
    WriteEndpoint("DELETE", "/api/categories/{category_pk}/", "outsider"),
    WriteEndpoint("POST", "/api/service-names/", "outsider"),
    WriteEndpoint("DELETE", "/api/service-names/{service_pk}/", "outsider"),
    WriteEndpoint("POST", "/api/exchange-rates/", "owner"),
    # Subscriptions (owner of plan_x)
    WriteEndpoint("POST", "/api/subscriptions/", "owner"),
    WriteEndpoint("PATCH", "/api/subscriptions/{plan_x}/", "owner", hostile_reject=False),
    WriteEndpoint("DELETE", "/api/subscriptions/{plan_x}/", "owner"),
    WriteEndpoint("POST", "/api/subscriptions/{plan_x}/price-changes/", "owner"),
    WriteEndpoint("POST", "/api/subscriptions/{plan_x}/pause/", "owner"),
    WriteEndpoint("POST", "/api/subscriptions/{plan_x}/resume/", "owner"),
    WriteEndpoint("POST", "/api/subscriptions/{plan_x}/cancel/", "owner"),
    WriteEndpoint("POST", "/api/subscriptions/{plan_x}/renew/", "owner"),
    WriteEndpoint("POST", "/api/subscriptions/{plan_x}/share/", "owner"),
    WriteEndpoint("POST", "/api/charges/generate/", "owner", hostile_reject=False),
    WriteEndpoint("PATCH", "/api/charges/{charge_x}/rate/", "owner"),
    # Sharing (owner)
    WriteEndpoint("PATCH", "/api/shared-plans/{plan_x}/", "owner"),
    WriteEndpoint("POST", "/api/shared-plans/{plan_x}/invites/", "owner"),
    WriteEndpoint("POST", "/api/shared-plans/{plan_x}/transfer/", "owner"),
    WriteEndpoint("PUT", "/api/shared-plans/{plan_x}/split/", "owner"),
    WriteEndpoint("POST", "/api/invites/{invite_pk}/cancel/", "owner", hostile_reject=False),
    WriteEndpoint("POST", "/api/invites/{invite_pk}/new-link/", "owner", hostile_reject=False),
    WriteEndpoint("POST", "/api/members/{member}/leave/", "owner"),
    WriteEndpoint("POST", "/api/members/{member}/replace/", "owner"),
    WriteEndpoint("POST", "/api/transfers/{transfer_pk}/cancel/", "owner"),
    WriteEndpoint("POST", "/api/transfers/{transfer_pk}/decline/", "member"),
    WriteEndpoint("POST", "/api/transfers/{transfer_pk}/accept/", "member"),
    # Sharing (member)
    WriteEndpoint("POST", "/api/shared-plans/{plan_x}/leave-request/", "member", hostile_reject=False),
    WriteEndpoint("DELETE", "/api/shared-plans/{plan_x}/leave-request/", "member", hostile_reject=False),
    WriteEndpoint("POST", "/api/me/invites/{invite_pk}/accept/", "outsider"),
    WriteEndpoint("POST", "/api/me/invites/{invite_pk}/decline/", "outsider"),
    # Token routes (auth where required)
    WriteEndpoint("POST", "/api/join/{join_token}/accept/", "outsider"),
    WriteEndpoint("POST", "/api/join/{join_token}/signup/", "anon"),
    WriteEndpoint("POST", "/api/invites/{invite_token}/accept/", "outsider"),
    WriteEndpoint("POST", "/api/invites/{invite_token}/decline/", "outsider"),
    WriteEndpoint("POST", "/api/invites/{invite_token}/signup/", "anon"),
    # Payments
    WriteEndpoint("POST", "/api/payments/", "member"),
    WriteEndpoint("POST", "/api/payments/{payment}/confirm/", "owner", hostile_reject=False),
    WriteEndpoint("POST", "/api/payments/{payment}/reject/", "owner"),
    WriteEndpoint("POST", "/api/payments/{payment}/reverse/", "owner", hostile_reject=False),
    WriteEndpoint("POST", "/api/payments/{payment}/waive/", "owner", hostile_reject=False),
    WriteEndpoint("POST", "/api/dues/{due_x}/mark-paid/", "owner"),
    WriteEndpoint("POST", "/api/dues/{due_x}/waive/", "owner"),
    WriteEndpoint("POST", "/api/dues/{due_x}/set-due/", "owner", hostile_reject=False),
    WriteEndpoint("POST", "/api/notifications/read-all/", "owner", hostile_reject=False),
)


def _user_for_role(world, role: Role):
    if role == "anon":
        return None
    return {
        "owner": world["owner"],
        "member": world["member"],
        "outsider": world["outsider"],
    }[role]


def _ensure_pending_payment(world) -> int:
    cache = world.setdefault("_robust_payment_id", None)
    if cache is not None:
        return cache
    due = world["due_x"]
    due.status = DueStatus.DUE
    due.save(update_fields=["status"])
    r = _submit(client_for(world["member"]), world["plan_x"].pk, [due.pk], transaction_id="ROBUSTP01")
    assert r.status_code == 201, r.content
    world["_robust_payment_id"] = r.json()["payment_id"]
    return world["_robust_payment_id"]


def _ensure_owner_notification(world) -> int:
    from notifications.models import Notification

    note = Notification.objects.filter(user=world["owner"]).order_by("-id").first()
    if note is None:
        note = Notification.objects.create(
            user=world["owner"],
            kind="test",
            title="t",
            body="b",
            link="",
        )
    return note.pk


def _ensure_user_category(world) -> int:
    from catalog.models import Category

    row = Category.objects.filter(is_preset=False, user=world["outsider"]).first()
    if row is None:
        from catalog import services

        row = services.create_category(world["outsider"], "RobustCat")
    return row.pk


def _ensure_user_service(world, category_pk: int) -> int:
    from catalog.models import ServiceName

    row = ServiceName.objects.filter(is_preset=False, user=world["outsider"], category_id=category_pk).first()
    if row is None:
        from catalog import services

        row = services.create_service_name(world["outsider"], "RobustSvc", category_pk)
    return row.pk


def _ensure_invite(world) -> int:
    from sharing.models import Invite

    cache = world.get("_robust_invite_pk")
    if cache is not None:
        return cache
    owner = client_for(world["owner"])
    r = owner.post(
        f"/api/shared-plans/{world['plan_x'].pk}/invites/",
        {"email": "robust-invite@example.com"},
        format="json",
    )
    if r.status_code == 201:
        world["_robust_invite_pk"] = r.json()["id"]
        return world["_robust_invite_pk"]
    invite = Invite.objects.filter(shared_plan=world["shared_x"]).order_by("-id").first()
    assert invite is not None
    world["_robust_invite_pk"] = invite.pk
    return invite.pk


def prepare_write_route(world, endpoint: WriteEndpoint) -> None:
    """Put related rows into states where hostile retries tend to reject, not succeed."""
    owner = client_for(world["owner"])
    plan_id = world["plan_x"].pk
    tmpl = endpoint.path_template
    if tmpl.endswith("/pause/") and endpoint.method == "POST":
        owner.post(f"/api/subscriptions/{plan_id}/pause/", {}, format="json")
    if tmpl.endswith("/resume/") and endpoint.method == "POST":
        owner.post(f"/api/subscriptions/{plan_id}/pause/", {}, format="json")
        owner.post(f"/api/subscriptions/{plan_id}/resume/", {}, format="json")
    if tmpl.endswith("/cancel/") and endpoint.method == "POST":
        owner.post(f"/api/subscriptions/{plan_id}/cancel/", {}, format="json")
    if "/payments/{payment}/confirm/" in tmpl and endpoint.method == "POST":
        pay_id = _ensure_pending_payment(world)
        owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    if "/payments/{payment}/reject/" in tmpl:
        _ensure_pending_payment(world)
    if "/payments/{payment}/reverse/" in tmpl and endpoint.method == "POST":
        pay_id = _ensure_pending_payment(world)
        owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
        owner.post(f"/api/payments/{pay_id}/reverse/", {}, format="json")
    if "/payments/{payment}/waive/" in tmpl:
        pay_id = _ensure_pending_payment(world)
        owner.post(f"/api/payments/{pay_id}/confirm/", {}, format="json")
    if "/dues/{due_x}/mark-paid/" in tmpl:
        due_id = world["due_x"].pk
        owner.post(
            f"/api/dues/{due_id}/mark-paid/",
            {"date": str(world["today"]), "method": "cash", "note": ""},
            format="json",
        )
    if "/dues/{due_x}/waive/" in tmpl:
        due = world["due_x"]
        due.refresh_from_db()
        if due.status != DueStatus.WAIVED:
            owner.post(f"/api/dues/{due.pk}/waive/", {"note": "prior"}, format="json")
    if "/dues/{due_x}/set-due/" in tmpl:
        due = world["due_x"]
        if due.status != DueStatus.PAID:
            owner.post(
                f"/api/dues/{due.pk}/mark-paid/",
                {"date": str(world["today"]), "method": "cash"},
                format="json",
            )
        owner.post(f"/api/dues/{due.pk}/set-due/", {}, format="json")


def resolve_write_path(world, template: str, *, method: str = "GET") -> str:
    ctx: dict[str, object] = {
        "plan_x": world["plan_x"].pk,
        "plan_y": world["plan_y"].pk,
        "member": world["member_row"].pk,
        "due_x": world["due_x"].pk,
        "charge_x": world["charge_x"].pk,
        "transfer_pk": 999_999_991,
        "invite_token": "robust-deadbeef",
        "join_token": "robust-deadbeef",
    }
    if "{payment}" in template:
        ctx["payment"] = _ensure_pending_payment(world)
    if "{notification}" in template:
        ctx["notification"] = _ensure_owner_notification(world)
    if "{category_pk}" in template:
        ctx["category_pk"] = (
            999_999_993 if method == "DELETE" else _ensure_user_category(world)
        )
    if "{service_pk}" in template:
        if method == "DELETE":
            ctx["service_pk"] = 999_999_994
        else:
            cat_pk = ctx.get("category_pk") or _ensure_user_category(world)
            ctx["service_pk"] = _ensure_user_service(world, int(cat_pk))
    if "{invite_pk}" in template:
        ctx["invite_pk"] = _ensure_invite(world)
    return template.format(**ctx)


def client_for_role(world, role: Role):
    user = _user_for_role(world, role)
    if user is None:
        from rest_framework.test import APIClient

        return APIClient()
    return client_for(user)