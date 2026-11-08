from django.utils import timezone


def today_dhaka():
    """Current calendar date in Asia/Dhaka (see TIME_ZONE in settings)."""
    return timezone.localdate()
