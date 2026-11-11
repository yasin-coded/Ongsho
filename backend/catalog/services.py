from django.db import IntegrityError, transaction

from catalog.models import Category, ServiceName
from catalog.selectors import category_visible_to_user
from core.exceptions import ConflictError, Forbidden, NotFound, ValidationFailed
from plans.models import Subscription

_NAME_MAX_LENGTH = Category._meta.get_field("name").max_length


def _validate_trimmed_name(name: str, field: str = "name") -> str:
    trimmed = name.strip()
    if not trimmed:
        raise ValidationFailed(
            "This field may not be blank.",
            fields={field: ["This field may not be blank."]},
        )
    if len(trimmed) > _NAME_MAX_LENGTH:
        raise ValidationFailed(
            f"Ensure this field has no more than {_NAME_MAX_LENGTH} characters.",
            fields={field: [f"Ensure this field has no more than {_NAME_MAX_LENGTH} characters."]},
        )
    return trimmed


@transaction.atomic
def create_category(user, name: str) -> Category:
    trimmed = _validate_trimmed_name(name)
    if Category.objects.filter(is_preset=True, user__isnull=True, name__iexact=trimmed).exists():
        raise ValidationFailed(
            "A category with this name already exists.",
            fields={"name": ["A category with this name already exists."]},
        )
    if Category.objects.filter(is_preset=False, user=user, name__iexact=trimmed).exists():
        raise ValidationFailed(
            "A category with this name already exists.",
            fields={"name": ["A category with this name already exists."]},
        )
    try:
        return Category.objects.create(user=user, name=trimmed, is_preset=False)
    except IntegrityError as exc:
        raise ValidationFailed(
            "A category with this name already exists.",
            fields={"name": ["A category with this name already exists."]},
        ) from exc


@transaction.atomic
def create_service_name(user, name: str, category_id: int) -> ServiceName:
    trimmed = _validate_trimmed_name(name)
    category = category_visible_to_user(user, category_id)
    if category is None:
        raise ValidationFailed(
            "Select a valid category.",
            fields={"category": ["Select a valid category."]},
        )
    if ServiceName.objects.filter(is_preset=True, user__isnull=True, category=category, name__iexact=trimmed).exists():
        raise ValidationFailed(
            "A service name with this name already exists in this category.",
            fields={"name": ["A service name with this name already exists in this category."]},
        )
    if ServiceName.objects.filter(is_preset=False, user=user, category=category, name__iexact=trimmed).exists():
        raise ValidationFailed(
            "A service name with this name already exists in this category.",
            fields={"name": ["A service name with this name already exists in this category."]},
        )
    try:
        return ServiceName.objects.create(user=user, category=category, name=trimmed, is_preset=False)
    except IntegrityError as exc:
        raise ValidationFailed(
            "A service name with this name already exists in this category.",
            fields={"name": ["A service name with this name already exists in this category."]},
        ) from exc


@transaction.atomic
def delete_category(user, pk: int) -> None:
    category = Category.objects.filter(pk=pk).first()
    if category is None:
        raise NotFound("Category not found.")
    if category.is_preset:
        raise Forbidden(
            "Preset categories cannot be deleted.",
            code="preset_not_deletable",
        )
    if category.user_id != user.pk:
        raise NotFound("Category not found.")
    other = Category.objects.filter(is_preset=True, user__isnull=True, name="Other").first()
    if other is None:
        raise ValidationFailed("Preset category Other is not available.")
    Subscription.objects.filter(owner=user, category=category).update(category=other)
    category.delete()


@transaction.atomic
def delete_service_name(user, pk: int) -> None:
    row = ServiceName.objects.filter(pk=pk).select_related("category").first()
    if row is None:
        raise NotFound("Service name not found.")
    if row.is_preset:
        raise Forbidden(
            "Preset service names cannot be deleted.",
            code="preset_not_deletable",
        )
    if row.user_id != user.pk:
        raise NotFound("Service name not found.")
    if Subscription.all_with_archived.filter(owner=user, service_name=row).exists():
        raise ConflictError(
            "This service name is used by a plan.",
            code="in_use",
            fields={"service_name": ["This service name is used by a plan."]},
        )
    row.delete()
