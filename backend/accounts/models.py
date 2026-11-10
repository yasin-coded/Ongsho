from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db.models.functions import Lower
from django.core.exceptions import ValidationError
from django.db import models

from accounts.constants import AVATAR_KEY_SET, DEFAULT_AVATAR_ID
from accounts.validators import validate_reminder_days


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("email_verified", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    email_verified = models.BooleanField(default=False)
    pending_email = models.EmailField(blank=True, default="")
    name = models.CharField(max_length=255)
    avatar_id = models.CharField(max_length=32, default=DEFAULT_AVATAR_ID)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    email_reminders = models.BooleanField(default=True)
    reminder_days = models.CharField(max_length=20, default="7,1")

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique"),
        ]

    def __str__(self) -> str:
        return self.email

    def clean(self):
        super().clean()
        if self.avatar_id not in AVATAR_KEY_SET:
            raise ValidationError({"avatar_id": "Must be one of avatar_1 through avatar_10."})
        try:
            validate_reminder_days(self.reminder_days)
        except ValidationError as exc:
            raise ValidationError({"reminder_days": exc.messages}) from exc

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.lower()
        if self.pending_email:
            self.pending_email = self.pending_email.lower()
        if self.avatar_id not in AVATAR_KEY_SET:
            raise ValidationError({"avatar_id": "Must be one of avatar_1 through avatar_10."})
        super().save(*args, **kwargs)
