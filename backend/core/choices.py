from django.db import models


class Currency(models.TextChoices):
    BDT = "BDT", "BDT"
    USD = "USD", "USD"


class PaymentMethod(models.TextChoices):
    BKASH = "bkash", "bKash"
    NAGAD = "nagad", "Nagad"
    ROCKET = "rocket", "Rocket"
    MOBILE_BANKING = "mobile_banking", "Mobile banking"
    BANK = "bank", "Bank"
    CASH = "cash", "Cash"
    OTHER = "other", "Other"
