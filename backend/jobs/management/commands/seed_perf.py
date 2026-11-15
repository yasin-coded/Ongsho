"""Bulk dev data for EXPLAIN and manual perf checks (DEBUG only)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from audit.models import AuditLog
from billing.models import Charge, ChargeStatus
from catalog.models import Category, ServiceName
from core.choices import Currency, PaymentMethod
from dues.models import Due, DueStatus
from notifications.models import Notification
from plans.models import CycleUnit, PlanMode, RenewalType, Subscription, SubscriptionStatus
from sharing.models import Member, MemberStatus, SharedPlan, SplitType


class Command(BaseCommand):
    help = "Seed large dev dataset for performance testing (requires DEBUG=True)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_perf refuses to run unless DEBUG is True.")
        streaming = Category.objects.filter(is_preset=True, name="Streaming").first()
        netflix = ServiceName.objects.filter(is_preset=True, name="Netflix", category=streaming).first()
        if not streaming or not netflix:
            raise CommandError("Run migrations/catalog presets first.")
        today = date.today()
        with transaction.atomic():
            users = []
            for i in range(50):
                email = f"perf{i}@example.com"
                if User.objects.filter(email=email).exists():
                    users.append(User.objects.get(email=email))
                else:
                    users.append(
                        User.objects.create_user(
                            email=email,
                            password="perfpass12345",
                            name=f"Perf {i}",
                            email_verified=True,
                        )
                    )
            audit_rows: list[AuditLog] = []
            notif_rows: list[Notification] = []
            for p in range(100):
                owner = users[p % len(users)]
                sub = Subscription.objects.create(
                    owner=owner,
                    service_name=netflix,
                    category=streaming,
                    plan_name=f"Perf plan {p}",
                    plan_mode=PlanMode.OWNER,
                    currency=Currency.BDT,
                    cycle_unit=CycleUnit.MONTH,
                    cycle_count=1,
                    anchor_day=5,
                    start_date=today - timedelta(days=180),
                    renewal_type=RenewalType.AUTO,
                    status=SubscriptionStatus.ACTIVE,
                    recommended_method=PaymentMethod.BKASH,
                    billing_from=today - timedelta(days=180),
                )
                shared = SharedPlan.objects.create(subscription=sub, split_type=SplitType.EQUAL, seats=8)
                members = []
                for m in range(6):
                    u = users[(p * 6 + m) % len(users)]
                    members.append(
                        Member(
                            shared_plan=shared,
                            user=u,
                            share_type=SplitType.EQUAL,
                            status=MemberStatus.ACTIVE,
                            joined_on=sub.start_date,
                        )
                    )
                Member.objects.bulk_create(members, ignore_conflicts=True)
                members = list(Member.objects.filter(shared_plan=shared))
                for month in range(12):
                    due = sub.start_date + timedelta(days=30 * month)
                    period_start = due
                    period_end = due + timedelta(days=29)
                    ch = Charge.objects.create(
                        subscription=sub,
                        period_start=period_start,
                        period_end=period_end,
                        due_date=due,
                        amount=Decimal("600.00"),
                        currency=Currency.BDT,
                        rate_used=None,
                        amount_bdt=Decimal("600.00"),
                        status=ChargeStatus.DUE,
                        locked=False,
                    )
                    Due.objects.bulk_create(
                        [
                            Due(charge=ch, member=mem, amount_bdt=Decimal("100.00"), status=DueStatus.DUE)
                            for mem in members
                        ],
                        ignore_conflicts=True,
                    )
            for i in range(5000):
                user = users[i % len(users)]
                notif_rows.append(
                    Notification(user=user, kind="perf", message=f"Perf message {i}", title="", payload={})
                )
                audit_rows.append(
                    AuditLog(
                        user=user,
                        action="perf.seed",
                        entity_type="subscription",
                        entity_id=i,
                        plan_id=(i % 100) + 1,
                        summary="",
                        created_at=timezone.now(),
                    )
                )
            Notification.objects.bulk_create(notif_rows, batch_size=500)
            AuditLog.objects.bulk_create(audit_rows, batch_size=500)
        self.stdout.write(self.style.SUCCESS("seed_perf completed"))