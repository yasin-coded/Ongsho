from django.db.models import Case, Exists, IntegerField, OuterRef, Q, Value, When

from catalog.models import Category, ServiceName
from plans.models import Subscription


def available_categories(user):
    in_use = Subscription.objects.filter(
        owner=user,
        archived_on__isnull=True,
        category_id=OuterRef("pk"),
    )
    return (
        Category.objects.filter(Q(is_preset=True, user__isnull=True) | Q(is_preset=False, user=user))
        .annotate(in_use=Exists(in_use))
        .order_by(Case(When(is_preset=True, then=Value(0)), default=Value(1), output_field=IntegerField()), "name")
    )


def available_service_names(user, category_id=None):
    in_use = Subscription.objects.filter(
        owner=user,
        archived_on__isnull=True,
        service_name_id=OuterRef("pk"),
    )
    qs = (
        ServiceName.objects.filter(
            Q(is_preset=True, user__isnull=True) | Q(is_preset=False, user=user)
        )
        .select_related("category")
        .annotate(in_use=Exists(in_use))
    )
    if category_id is not None:
        qs = qs.filter(category_id=category_id)
    return qs.order_by(
        Case(When(is_preset=True, then=Value(0)), default=Value(1), output_field=IntegerField()),
        "name",
    )


def category_visible_to_user(user, category_id: int) -> Category | None:
    return (
        Category.objects.filter(pk=category_id)
        .filter(Q(is_preset=True, user__isnull=True) | Q(is_preset=False, user=user))
        .first()
    )
