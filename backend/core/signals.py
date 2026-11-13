from django.dispatch import Signal

plan_prices_changed = Signal()
plan_status_changed = Signal()
plan_created = Signal()
charges_created = Signal()
charge_amount_changed = Signal()

plan_deleted = Signal()
member_joined = Signal()
member_leaving = Signal()
split_changed = Signal()
