"""Login must run password verification on unknown, inactive, and unverified accounts."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from accounts import services as account_services
from core.exceptions import Forbidden, Unauthorized
from core.lockout import LOGIN_INVALID_MESSAGE

User = get_user_model()
PASSWORD = "HorseBatteryStaple99"


@pytest.mark.django_db
def test_login_check_password_unknown_email():
    with patch("django.contrib.auth.hashers.check_password", return_value=False) as verify:
        with pytest.raises(Unauthorized) as exc:
            account_services.login_user(email="nobody@example.com", password=PASSWORD)
    verify.assert_called_once()
    assert exc.value.code == "invalid_credentials"
    assert exc.value.message == LOGIN_INVALID_MESSAGE


@pytest.mark.django_db
def test_login_check_password_inactive_user():
    User.objects.create_user(
        email="inactive@example.com", password=PASSWORD, name="I", email_verified=True, is_active=False
    )
    with patch("django.contrib.auth.hashers.check_password", return_value=False) as verify:
        with pytest.raises(Unauthorized):
            account_services.login_user(email="inactive@example.com", password=PASSWORD)
    assert verify.call_count >= 1


@pytest.mark.django_db
def test_login_check_password_unverified_after_verify():
    User.objects.create_user(email="unv@example.com", password=PASSWORD, name="U", email_verified=False)
    with patch("django.contrib.auth.hashers.check_password", return_value=True) as verify:
        with pytest.raises(Forbidden) as exc:
            account_services.login_user(email="unv@example.com", password=PASSWORD)
    verify.assert_called_once()
    assert exc.value.code == "email_not_verified"