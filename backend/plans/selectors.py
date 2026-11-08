from plans.models import ExchangeRate


def exchange_rates_for_user(user):
    return ExchangeRate.objects.filter(user=user).order_by("-rate_date", "-id")
