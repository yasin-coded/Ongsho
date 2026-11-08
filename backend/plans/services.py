from decimal import Decimal

from core.dates import today_dhaka
from plans.models import ExchangeRate


def create_exchange_rate(user, *, rate_date, usd_to_bdt: Decimal) -> ExchangeRate:
    return ExchangeRate.objects.create(
        user=user,
        rate_date=rate_date,
        usd_to_bdt=usd_to_bdt,
        source="manual",
    )
