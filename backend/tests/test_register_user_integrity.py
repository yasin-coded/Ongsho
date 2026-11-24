"""register_user duplicate handling and concurrent registration."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from accounts import services as account_services
from core.exceptions import ValidationFailed

from tests.helpers import run_concurrently
from tests.test_subscriptions import WORLD_PASS

User = get_user_model()
STRONG_PASSWORD = WORLD_PASS


@pytest.mark.django_db
def test_sequential_duplicate_registration():
    account_services.register_user(
        email="dup-seq@example.com", password=STRONG_PASSWORD, name="First"
    )
    with pytest.raises(ValidationFailed) as exc:
        account_services.register_user(
            email="dup-seq@example.com", password=STRONG_PASSWORD, name="Second"
        )
    assert exc.value.code == "validation_failed"
    assert "email" in exc.value.fields
    assert User.objects.filter(email__iexact="dup-seq@example.com").count() == 1


@pytest.mark.django_db
def test_case_insensitive_duplicate_rejected():
    account_services.register_user(
        email="MixedCase@Example.com", password=STRONG_PASSWORD, name="First"
    )
    with pytest.raises(ValidationFailed) as exc:
        account_services.register_user(
            email="mixedcase@example.com", password=STRONG_PASSWORD, name="Second"
        )
    assert exc.value.code == "validation_failed"
    assert User.objects.filter(email__iexact="mixedcase@example.com").count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_register_single_account():
    email = "race-new@example.com"

    def attempt():
        return account_services.register_user(email=email, password=STRONG_PASSWORD, name="Race")

    results, errors = run_concurrently([attempt] * 4, transaction=True)
    successes = [r for r in results if r is not None]
    failures = [e for e in errors if e is not None]
    assert len(successes) == 1
    assert len(failures) == 3
    for exc in failures:
        assert isinstance(exc, ValidationFailed)
        assert exc.code == "validation_failed"
        assert "email" in exc.fields
    assert User.objects.filter(email__iexact=email, is_active=True).count() == 1


@pytest.mark.django_db
def test_integrity_collision_maps_to_validation_failed(monkeypatch):
    def create_user_duplicate(*args, **kwargs):
        raise IntegrityError('duplicate key value violates unique constraint "accounts_user_email_ci_unique"')

    monkeypatch.setattr(User.objects, "create_user", create_user_duplicate)
    with pytest.raises(ValidationFailed) as exc:
        account_services.register_user(email="race-db@example.com", password=STRONG_PASSWORD, name="First")
    assert exc.value.code == "validation_failed"
    assert "email" in exc.value.fields


@pytest.mark.django_db
def test_unrelated_integrity_error_propagates(monkeypatch):
    def fail_create(*args, **kwargs):
        raise IntegrityError('violates foreign key constraint "other_table_fkey"')

    monkeypatch.setattr(User.objects, "create_user", fail_create)
    with pytest.raises(IntegrityError, match="other_table_fkey"):
        account_services.register_user(
            email="unrelated@example.com", password=STRONG_PASSWORD, name="X"
        )