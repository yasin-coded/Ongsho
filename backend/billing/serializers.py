from rest_framework import serializers

from billing.models import Charge


class ChargePlanSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    plan_name = serializers.CharField()


class ChargeSerializer(serializers.ModelSerializer):
    plan = serializers.SerializerMethodField()
    rate_used = serializers.DecimalField(
        max_digits=12, decimal_places=4, allow_null=True, coerce_to_string=True
    )
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=True)
    amount_bdt = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=True)
    has_payments = serializers.BooleanField(source="_has_payments")

    class Meta:
        model = Charge
        fields = (
            "id",
            "plan",
            "period_start",
            "period_end",
            "due_date",
            "amount",
            "currency",
            "rate_used",
            "amount_bdt",
            "status",
            "locked",
            "has_payments",
        )

    def get_plan(self, obj):
        sub = obj.subscription
        return {"id": sub.pk, "plan_name": sub.plan_name}
