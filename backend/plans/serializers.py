from decimal import Decimal

from rest_framework import serializers

from core.dates import today_dhaka
from plans.models import ExchangeRate


class ExchangeRateSerializer(serializers.ModelSerializer):
    usd_to_bdt = serializers.DecimalField(max_digits=12, decimal_places=4, coerce_to_string=True)

    class Meta:
        model = ExchangeRate
        fields = ("id", "rate_date", "usd_to_bdt", "source")
        read_only_fields = fields


class ExchangeRateCreateSerializer(serializers.Serializer):
    rate_date = serializers.DateField()
    usd_to_bdt = serializers.DecimalField(max_digits=12, decimal_places=4)
    source = serializers.CharField(required=False, allow_blank=True, write_only=True)
    user = serializers.IntegerField(required=False, write_only=True)

    def validate_usd_to_bdt(self, value):
        if value <= 0:
            raise serializers.ValidationError("Rate must be greater than zero.")
        quantized = value.quantize(Decimal("0.0001"))
        if value != quantized:
            raise serializers.ValidationError("Enter a number with at most 4 decimal places.")
        return quantized

    def validate_rate_date(self, value):
        if value > today_dhaka():
            raise serializers.ValidationError("Rate date cannot be in the future.")
        return value

    def validate(self, attrs):
        attrs.pop("source", None)
        attrs.pop("user", None)
        return attrs
