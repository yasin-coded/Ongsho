from django.conf import settings
from django.db import models
from django.db.models import Q


class Category(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="categories",
    )
    name = models.CharField(max_length=128)
    is_preset = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "categories"
        constraints = [
            models.CheckConstraint(
                condition=(
                    (Q(is_preset=True) & Q(user__isnull=True)) | (Q(is_preset=False) & Q(user__isnull=False))
                ),
                name="catalog_category_preset_user",
            ),
            models.UniqueConstraint(
                fields=["name"],
                condition=Q(is_preset=True, user__isnull=True),
                name="catalog_category_preset_name_unique",
            ),
            models.UniqueConstraint(
                fields=["user", "name"],
                condition=Q(is_preset=False, user__isnull=False),
                name="catalog_category_user_name_unique",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class ServiceName(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="service_names",
    )
    category = models.ForeignKey("catalog.Category", on_delete=models.PROTECT, related_name="service_names")
    name = models.CharField(max_length=128)
    is_preset = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    (Q(is_preset=True) & Q(user__isnull=True)) | (Q(is_preset=False) & Q(user__isnull=False))
                ),
                name="catalog_servicename_preset_user",
            ),
            models.UniqueConstraint(
                fields=["category", "name"],
                condition=Q(is_preset=True, user__isnull=True),
                name="catalog_servicename_preset_unique",
            ),
            models.UniqueConstraint(
                fields=["user", "category", "name"],
                condition=Q(is_preset=False, user__isnull=False),
                name="catalog_servicename_user_unique",
            ),
        ]

    def __str__(self) -> str:
        return self.name
