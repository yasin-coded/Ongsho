from __future__ import annotations

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from core.dev_db_guard import assert_local_dev_database


def test_seed_perf_refuses_when_debug_false():
    with override_settings(DEBUG=False):
        with pytest.raises(CommandError, match="DEBUG"):
            call_command("seed_perf")


@override_settings(DEBUG=True, DATABASES={"default": {"ENGINE": "django.db.backends.postgresql", "HOST": "db.example.com", "NAME": "x", "USER": "u", "PASSWORD": "p"}})
def test_seed_perf_refuses_remote_host():
    with pytest.raises(CommandError, match="host 'db.example.com'"):
        call_command("seed_perf")


@override_settings(DEBUG=True, DATABASES={"default": {"ENGINE": "django.db.backends.postgresql", "HOST": "127.0.0.1", "NAME": "x", "USER": "u", "PASSWORD": "p"}})
def test_assert_local_allows_loopback():
    assert_local_dev_database("test_tool")


@override_settings(DEBUG=True, DATABASES={"default": {"ENGINE": "django.db.backends.postgresql", "HOST": "neon.tech", "NAME": "x", "USER": "u", "PASSWORD": "p"}})
def test_assert_local_remote_override_env(monkeypatch):
    monkeypatch.setenv("ALLOW_SEED_PERF_REMOTE", "1")
    assert_local_dev_database("test_tool")


def test_explain_hot_queries_guard_import():
    from core.dev_db_guard import assert_local_dev_database_or_exit

    assert callable(assert_local_dev_database_or_exit)