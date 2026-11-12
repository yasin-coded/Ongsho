from decimal import Decimal

from django.dispatch import receiver

from core.money import format_bdt, quantize_money
from core.signals import plan_deleted, plan_prices_changed
from plans.models import PriceChange
from sharing import services as sharing_services
from sharing.models import Member, MemberStatus, SplitType


@receiver(plan_deleted)
def on_plan_deleted(sender, *, plan_id, plan_name, owner, member_user_ids, archived, **kwargs):
    from core.notify import notify

    if archived:
        message = "The plan was removed from your dashboard. Its payment history is kept."
    else:
        message = "The plan had no confirmed payments, so it was removed for everyone."
    title = f"{sharing_services._first_name(owner)} deleted {plan_name}"
    for user_id in member_user_ids:
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.filter(pk=user_id).first()
        if user:
            notify(
                user,
                "plan_deleted",
                title,
                message,
                link="/app/shared-plans",
                payload={"plan_id": plan_id},
            )

@receiver(plan_prices_changed)
def on_plan_prices_changed(sender, *, plan, **kwargs):
    from core.notify import notify

    changes = list(PriceChange.objects.filter(subscription=plan).order_by("-effective_from", "-id")[:2])
    if len(changes) < 2:
        return
    new_pc, old_pc = changes[0], changes[1]
    shared = getattr(plan, "shared_plan", None)
    if shared is None:
        from sharing.models import SharedPlan

        shared = SharedPlan.objects.filter(subscription=plan).first()
    if shared is None:
        return
    from plans.selectors import price_now_dict

    new_price = price_now_dict(plan)
    if not new_price:
        return
    new_bdt = Decimal(str(new_price["amount_bdt"]))
    old_bdt = old_pc.amount
    if plan.currency == "USD":
        from plans.selectors import price_now_dict as _  # noqa

        old_bdt = old_pc.amount  # simplified; compare in plan currency messaging
    members = Member.objects.filter(shared_plan=shared, status=MemberStatus.ACTIVE).exclude(user=plan.owner)
    if not members.exists():
        return
    title = f"{plan.plan_name} costs {format_bdt(new_bdt)} from {new_pc.effective_from}"
    if shared.split_type == SplitType.EQUAL:
        old_seat = quantize_money(old_bdt / Decimal(shared.seats))
        new_seat = quantize_money(new_bdt / Decimal(shared.seats))
        message = (
            f"Each of the {shared.seats} seats moves from {format_bdt(old_seat)} "
            f"to {format_bdt(new_seat)}. Old months keep the old price."
        )
    else:
        message = "The owner will update each person's amount."
    for member in members:
        notify(
            member.user,
            "price_change",
            title,
            message,
            link=f"/app/shared-plans/{plan.pk}",
            payload={"plan_id": plan.pk},
        )
