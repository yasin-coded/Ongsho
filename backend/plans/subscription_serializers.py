from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from catalog.models import Category
from catalog.selectors import category_visible_to_user
from core.choices import Currency, PaymentMethod
from core.dates import today_dhaka
from core.money import quantize_money
from plans.models import CycleUnit, PlanMode, PriceChange, RenewalType, Subscription
from plans.selectors import current_amount_for_subscription, service_name_for_user

CYCLE_UNITS = {c.value for c in CycleUnit}
LOCKED_PATCH_FIELDS = frozenset(
    {
        "currency",
        "cycle_unit",
        "cycle_count",
        "start_date",
        "trial_end_date",
        "status",
        "owner",
        "anchor_day",
        "archived_on",
        "amount",
        "exchange_rate",
    }
)


def _validate_money_amount(value, field="amount"):
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise serializers.ValidationError("Enter a valid number.")
    if dec <= 0:
        raise serializers.ValidationError("Amount must be greater than zero.")
    q = quantize_money(dec)
    if dec != q:
        raise serializers.ValidationError("Enter a number with at most 2 decimal places.")
    return q


def _validate_exchange_rate(value):
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise serializers.ValidationError("Enter a valid number.")
    if dec <= 0:
        raise serializers.ValidationError("Rate must be greater than zero.")
    q = dec.quantize(Decimal("0.0001"))
    if dec != q:
        raise serializers.ValidationError("Enter a number with at most 4 decimal places.")
    return q


class NestedNameSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class SubscriptionDetailSerializer(serializers.ModelSerializer):
    service_name = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()
    amount_bdt_preview = serializers.CharField(required=False, read_only=True)
    pending_invites = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()
    next_renewal = serializers.SerializerMethodField()
    ends_on = serializers.DateField(source="cancelled_on", read_only=True)
    paused_on = serializers.DateField(read_only=True)
    trial_end_date = serializers.DateField(read_only=True)
    price_now = serializers.SerializerMethodField()
    monthly_cost = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = (
            "id",
            "service_name",
            "category",
            "plan_name",
            "plan_mode",
            "note",
            "currency",
            "cycle_unit",
            "cycle_count",
            "anchor_day",
            "start_date",
            "trial_end_date",
            "renewal_type",
            "end_date",
            "status",
            "recommended_method",
            "rarely_used",
            "amount",
            "amount_bdt_preview",
            "pending_invites",
            "member_count",
            "next_renewal",
            "ends_on",
            "paused_on",
            "price_now",
            "monthly_cost",
        )

    def get_service_name(self, obj):
        return {"id": obj.service_name_id, "name": obj.service_name.name}

    def get_category(self, obj):
        return {"id": obj.category_id, "name": obj.category.name}

    def get_amount(self, obj):
        if hasattr(obj, "current_amount"):
            if obj.current_amount is None:
                return None
            return str(quantize_money(obj.current_amount))
        amount = current_amount_for_subscription(obj)
        return str(quantize_money(amount)) if amount is not None else None

    def get_pending_invites(self, obj):
        from django.core.exceptions import ObjectDoesNotExist
        from sharing.models import Invite, InviteStatus

        try:
            shared = obj.shared_plan
        except ObjectDoesNotExist:
            return []
        return list(
            Invite.objects.filter(shared_plan=shared, status=InviteStatus.PENDING)
            .order_by("email")
            .values_list("email", flat=True)
        )

    def get_member_count(self, obj):
        from django.core.exceptions import ObjectDoesNotExist
        from sharing.models import Member, MemberStatus

        try:
            shared = obj.shared_plan
        except ObjectDoesNotExist:
            return 0
        return Member.objects.filter(
            shared_plan=shared,
            status__in=(MemberStatus.ACTIVE, MemberStatus.LEAVE_REQUESTED),
        ).count()

    def _price_block(self, obj):
        cache = getattr(obj, "_price_block_cache", None)
        if cache is not None:
            return cache
        from plans import selectors as plan_selectors

        cache = plan_selectors.price_now_dict(obj)
        obj._price_block_cache = cache
        return cache

    def get_next_renewal(self, obj):
        from plans import selectors as plan_selectors

        return plan_selectors.display_next_renewal(obj)

    def get_price_now(self, obj):
        data = self._price_block(obj)
        if data is None:
            return None
        return {k: data[k] for k in ("amount", "currency", "rate", "amount_bdt")}

    def get_monthly_cost(self, obj):
        data = self._price_block(obj)
        if data is None:
            return None
        return data.get("monthly_cost_bdt")


class SubscriptionListSerializer(SubscriptionDetailSerializer):
    class Meta(SubscriptionDetailSerializer.Meta):
        fields = tuple(
            f
            for f in SubscriptionDetailSerializer.Meta.fields
            if f not in ("pending_invites", "member_count")
        )


class SubscriptionCreateSerializer(serializers.Serializer):
    service_name = serializers.IntegerField()
    category = serializers.IntegerField(required=False, allow_null=True)
    plan_name = serializers.CharField(max_length=Subscription._meta.get_field("plan_name").max_length)
    plan_mode = serializers.ChoiceField(choices=PlanMode.choices)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    currency = serializers.ChoiceField(choices=Currency.choices, default=Currency.BDT)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    exchange_rate = serializers.DecimalField(
        max_digits=12, decimal_places=4, required=False, allow_null=True
    )
    cycle_unit = serializers.CharField()
    cycle_count = serializers.IntegerField(default=1, min_value=1)
    start_date = serializers.DateField()
    trial_end_date = serializers.DateField(required=False, allow_null=True)
    renewal_type = serializers.ChoiceField(choices=RenewalType.choices)
    end_date = serializers.DateField(required=False, allow_null=True)
    recommended_method = serializers.ChoiceField(choices=PaymentMethod.choices)
    rarely_used = serializers.BooleanField(default=False)
    next_renewal_date = serializers.DateField(required=False, allow_null=True, write_only=True)
    owner = serializers.IntegerField(required=False, write_only=True)
    status = serializers.CharField(required=False, write_only=True)
    anchor_day = serializers.IntegerField(required=False, write_only=True)
    archived_on = serializers.DateTimeField(required=False, write_only=True)

    def validate_next_renewal_date(self, value):
        if value is None:
            return value
        if value <= today_dhaka():
            return value
        raise serializers.ValidationError("Next renewal date must be today or earlier.")

    def validate_plan_name(self, value):
        trimmed = value.strip()
        if not trimmed:
            raise serializers.ValidationError("This field may not be blank.")
        max_len = Subscription._meta.get_field("plan_name").max_length
        if len(trimmed) > max_len:
            raise serializers.ValidationError(f"Ensure this field has no more than {max_len} characters.")
        return trimmed

    def validate_note(self, value):
        return (value or "").strip()

    def validate_amount(self, value):
        return _validate_money_amount(value)

    def validate_cycle_unit(self, value):
        if value not in CYCLE_UNITS:
            raise serializers.ValidationError("Invalid cycle unit.")
        return value

    def validate(self, attrs):
        attrs.pop("owner", None)
        attrs.pop("status", None)
        attrs.pop("anchor_day", None)
        attrs.pop("archived_on", None)

        user = self.context["request"].user
        service_name_id = attrs["service_name"]
        sn = service_name_for_user(user, service_name_id)
        if sn is None:
            raise serializers.ValidationError({"service_name": ["Select a valid service name."]})
        attrs["service_name_id"] = attrs.pop("service_name")

        cat_id = attrs.pop("category", None)
        if cat_id is not None:
            category = category_visible_to_user(user, cat_id)
            if category is None:
                raise serializers.ValidationError({"category": ["Select a valid category."]})
            attrs["category"] = category

        currency = attrs["currency"]
        rate = attrs.get("exchange_rate")
        if currency == Currency.BDT:
            if rate is not None:
                raise serializers.ValidationError(
                    {"exchange_rate": ["Exchange rate must not be sent for BDT plans."]}
                )
        elif currency == Currency.USD:
            if rate is None:
                raise serializers.ValidationError({"exchange_rate": ["This field is required for USD plans."]})
            attrs["exchange_rate"] = _validate_exchange_rate(rate)

        renewal = attrs["renewal_type"]
        end_date = attrs.get("end_date")
        start_date = attrs["start_date"]
        if renewal == RenewalType.FIXED_TERM:
            if not end_date:
                raise serializers.ValidationError({"end_date": ["This field is required for fixed-term plans."]})
            if end_date <= start_date:
                raise serializers.ValidationError({"end_date": ["End date must be after the start date."]})
        else:
            if end_date is not None:
                raise serializers.ValidationError({"end_date": ["End date must not be set for auto-renew plans."]})

        trial_end = attrs.get("trial_end_date")
        if trial_end and trial_end < start_date:
            raise serializers.ValidationError(
                {"trial_end_date": ["Trial end date cannot be before the start date."]}
            )
        return attrs


class SubscriptionPatchSerializer(serializers.Serializer):
    plan_name = serializers.CharField(max_length=Subscription._meta.get_field("plan_name").max_length, required=False)
    note = serializers.CharField(required=False, allow_blank=True)
    service_name = serializers.IntegerField(required=False)
    category = serializers.IntegerField(required=False)
    recommended_method = serializers.ChoiceField(choices=PaymentMethod.choices, required=False)
    rarely_used = serializers.BooleanField(required=False)
    renewal_type = serializers.ChoiceField(choices=RenewalType.choices, required=False)
    end_date = serializers.DateField(required=False, allow_null=True)
    plan_mode = serializers.CharField(required=False)
    currency = serializers.CharField(required=False)
    cycle_unit = serializers.CharField(required=False)
    cycle_count = serializers.IntegerField(required=False)
    start_date = serializers.DateField(required=False)
    trial_end_date = serializers.DateField(required=False, allow_null=True)
    status = serializers.CharField(required=False)
    owner = serializers.IntegerField(required=False)
    anchor_day = serializers.IntegerField(required=False)
    archived_on = serializers.DateTimeField(required=False)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    exchange_rate = serializers.DecimalField(max_digits=12, decimal_places=4, required=False)
    next_renewal_date = serializers.DateField(required=False)

    def validate(self, attrs):
        user = self.context["request"].user
        sub = self.context.get("subscription")
        if "service_name" in attrs:
            sn = service_name_for_user(user, attrs["service_name"])
            if sn is None:
                raise serializers.ValidationError({"service_name": ["Select a valid service name."]})
            attrs["service_name"] = sn
        if "category" in attrs:
            cat = category_visible_to_user(user, attrs["category"])
            if cat is None:
                raise serializers.ValidationError({"category": ["Select a valid category."]})
            attrs["category"] = cat
        renewal = attrs.get("renewal_type", sub.renewal_type if sub else None)
        end_date = attrs["end_date"] if "end_date" in attrs else (sub.end_date if sub else None)
        start_date = sub.start_date if sub else None
        if renewal == RenewalType.AUTO and end_date is not None:
            raise serializers.ValidationError({"end_date": ["End date must not be set for auto-renew plans."]})
        if renewal == RenewalType.FIXED_TERM:
            if end_date is None:
                raise serializers.ValidationError({"end_date": ["This field is required for fixed-term plans."]})
            if start_date and end_date <= start_date:
                raise serializers.ValidationError({"end_date": ["End date must be after the start date."]})
        if "plan_name" in attrs:
            trimmed = attrs["plan_name"].strip()
            if not trimmed:
                raise serializers.ValidationError({"plan_name": ["This field may not be blank."]})
            attrs["plan_name"] = trimmed
        if "note" in attrs:
            attrs["note"] = attrs["note"].strip()
        return attrs


class SubscriptionDeleteSerializer(serializers.Serializer):
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        required=False,
        allow_blank=True,
        allow_null=True,
        default="",
    )


class PriceChangeSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=True)

    class Meta:
        model = PriceChange
        fields = ("id", "amount", "currency", "effective_from")
        read_only_fields = ("id", "currency", "effective_from")


class SubscriptionRenewSerializer(serializers.Serializer):
    end_date = serializers.DateField()


class PriceChangeCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    effective_from = serializers.DateField()
    exchange_rate = serializers.DecimalField(
        max_digits=12, decimal_places=4, required=False, allow_null=True
    )
    currency = serializers.CharField(required=False, write_only=True)

    def validate_amount(self, value):
        return _validate_money_amount(value)

    def validate_effective_from(self, value):
        from core.dates import today_dhaka

        if value < today_dhaka():
            raise serializers.ValidationError("Effective date cannot be before today.")
        return value

    def validate(self, attrs):
        attrs.pop("currency", None)
        rate = attrs.get("exchange_rate")
        if rate is not None:
            attrs["exchange_rate"] = _validate_exchange_rate(rate)
        return attrs
