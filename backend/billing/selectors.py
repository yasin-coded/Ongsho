from django.db.models import Exists, OuterRef, Q

from billing.models import Charge
from core.exceptions import NotFound
from core.schedule import Schedule


def schedule_for_subscription(sub) -> Schedule:
    return Schedule(
        start_date=sub.start_date,
        trial_end_date=sub.trial_end_date,
        anchor_day=sub.anchor_day,
        cycle_unit=sub.cycle_unit,
        cycle_count=sub.cycle_count,
        renewal_type=sub.renewal_type,
        end_date=sub.end_date,
        paused_on=sub.paused_on,
        cancelled_on=sub.cancelled_on,
        status=sub.status,
        billing_from=sub.billing_from,
    )


def owned_charge(user, charge_id: int) -> Charge:
    row = (
        Charge.objects.filter(pk=charge_id, subscription__owner=user, subscription__archived_on__isnull=True)
        .select_related("subscription")
        .first()
    )
    if row is None:
        raise NotFound("Charge not found.")
    return row


def owner_charges_qs(user, *, params: dict):
    from payments.models import PaymentAllocation
    from sharing.models import Member

    owner_seat = Member.objects.filter(shared_plan__subscription_id=OuterRef("subscription_id"), user=user)
    non_owner_payment = PaymentAllocation.objects.filter(
        due__charge_id=OuterRef("pk"),
        payment__member__shared_plan__subscription_id=OuterRef("subscription_id"),
    ).exclude(payment__member__user=user)
    qs = (
        Charge.objects.filter(subscription__owner=user, subscription__archived_on__isnull=True)
        .select_related("subscription")
        .annotate(_has_payments=Exists(non_owner_payment))
        .order_by("-due_date", "-id")
    )
    if plan := params.get("plan"):
        qs = qs.filter(subscription_id=plan)
    if status := params.get("status"):
        qs = qs.filter(status=status)
    month = params.get("month")
    if month:
        qs = qs.filter(due_date__year=month.year, due_date__month=month.month)
    return qs
