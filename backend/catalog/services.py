from django.db import IntegrityError, transaction

from catalog.models import Category, ServiceName
from catalog.selectors import category_visible_to_user
from core.exceptions import ValidationFailed

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
