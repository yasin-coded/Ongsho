from __future__ import annotations

from django.dispatch import receiver

from core.notify import notify, resolve_notifications
from core.signals import ownership_transferred
from payments.models import Payment, ReviewStatus
from payments.services import _first_name, _method_label
from core.money import format_bdt


@receiver(ownership_transferred)
def on_ownership_transferred_payments(sender, *, plan, old_owner, new_owner, today, **kwargs):
    try:
        shared = plan.shared_plan
    except Exception:
        return
    pending = Payment.objects.filter(shared_plan=shared, review_status=ReviewStatus.PENDING).select_related(
        "member", "member__user"
    )
    for payment in pending:
        resolve_notifications("payment", payment_id=payment.pk)
        payer = payment.member.user
        notify(
            new_owner,
            "payment_submitted",
            f"{_first_name(payer)} sent a transaction ID",
            f"{plan.plan_name} · {_method_label(payment.method)} · ID {payment.transaction_id} · {format_bdt(payment.amount)}",
            link=f"/app/plans/{plan.pk}/review",
            payload={
                "action": {"type": "payment", "payment_id": payment.pk, "plan_id": plan.pk},
                "plan_id": plan.pk,
            },
        )
