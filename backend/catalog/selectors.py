from django.db.models import Case, IntegerField, Q, Value, When

from catalog.models import Category, ServiceName


def available_categories(user):
    return (
        Category.objects.filter(Q(is_preset=True, user__isnull=True) | Q(is_preset=False, user=user))
        .order_by(Case(When(is_preset=True, then=Value(0)), default=Value(1), output_field=IntegerField()), "name")
    )


def available_service_names(user, category_id=None):
    qs = ServiceName.objects.filter(
        Q(is_preset=True, user__isnull=True) | Q(is_preset=False, user=user)
    ).select_related("category")
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
