from __future__ import annotations

from django.dispatch import receiver

from core.signals import charge_amount_changed, charges_created, member_joined, member_leaving, split_changed
from dues import services as dues_services


@receiver(charges_created)
def on_charges_created(sender, *, charges, **kwargs):
    for charge in charges:
        dues_services.create_dues_for_charge(charge)


@receiver(member_joined)
def on_member_joined(sender, *, member, **kwargs):
    from core.dates import today_dhaka

    today = today_dhaka()
    plan = member.shared_plan.subscription
    for charge in dues_services.unlocked_charges_for_plan(plan, today):
        dues_services.recalculate_dues(charge, today)


@receiver(member_leaving)
def on_member_leaving(sender, *, member, leave_date, unpaid, **kwargs):
    today = kwargs.get("today")
    if today is None:
        from core.dates import today_dhaka

        today = today_dhaka()
    plan = member.shared_plan.subscription
    for charge in dues_services.unlocked_charges_for_plan(plan, today):
        dues_services.recalculate_dues(charge, today)
    owner = plan.owner
    dues_services.apply_leave_unpaid(member, today=today, unpaid=unpaid, actor=owner)


@receiver(split_changed)
def on_split_changed(sender, *, plan, today, **kwargs):
    dues_services.recalculate_plan_dues(plan, today)


@receiver(charge_amount_changed)
def on_charge_amount_changed(sender, *, charge, **kwargs):
    from core.dates import today_dhaka

    dues_services.recalculate_dues(charge, today_dhaka(), force=True)
