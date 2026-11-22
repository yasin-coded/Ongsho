import os
from unittest.mock import patch

import pytest

from config import settings

DIRECT = "postgresql://main:mainpass@ep-main.region.aws.neon.tech/neondb?sslmode=require"
POOLED = "postgresql://pool:poolpass@ep-pooler.region.aws.neon.tech/neondb?sslmode=require"
TEST_ONLY = "postgresql://testuser:testpass@ep-test.region.aws.neon.tech/test_neondb?sslmode=require"
MIGRATE = "postgresql://owner:ownerpass@ep-owner.region.aws.neon.tech/neondb?sslmode=require"


def _config(env: dict, *, running_pytest: bool, direct_url: bool) -> dict:
    with patch.dict(os.environ, env, clear=True):
        with patch.object(settings, "_running_pytest", return_value=running_pytest):
            with patch.object(settings, "_use_direct_database_url", return_value=direct_url):
                return settings._database_config()


def test_pytest_uses_test_database_url_when_set():
    cfg = _config(
        {"TEST_DATABASE_URL": TEST_ONLY, "DATABASE_URL": DIRECT},
        running_pytest=True,
        direct_url=True,
    )
    assert cfg["NAME"] == "test_neondb"
    assert cfg["USER"] == "testuser"
    assert cfg.get("DISABLE_SERVER_SIDE_CURSORS") is not True


def test_pytest_without_test_url_uses_database_url():
    cfg = _config({"DATABASE_URL": DIRECT}, running_pytest=True, direct_url=True)
    assert cfg["NAME"] == "neondb"
    assert cfg["USER"] == "main"


def test_non_pytest_ignores_test_database_url():
    cfg = _config(
        {"TEST_DATABASE_URL": TEST_ONLY, "DATABASE_URL_POOLED": POOLED},
        running_pytest=False,
        direct_url=False,
    )
    assert cfg["NAME"] == "neondb"
    assert cfg["USER"] == "pool"
    assert cfg["DISABLE_SERVER_SIDE_CURSORS"] is True
    assert cfg["CONN_MAX_AGE"] == 60
    assert cfg["CONN_HEALTH_CHECKS"] is True


def test_pooled_conn_max_age_from_env():
    cfg = _config(
        {"DATABASE_URL_POOLED": POOLED, "DB_CONN_MAX_AGE": "120"},
        running_pytest=False,
        direct_url=False,
    )
    assert cfg["CONN_MAX_AGE"] == 120


def test_direct_connection_zero_conn_max_age():
    cfg = _config(
        {"DATABASE_URL": DIRECT},
        running_pytest=False,
        direct_url=True,
    )
    assert cfg["CONN_MAX_AGE"] == 0
    assert cfg.get("CONN_HEALTH_CHECKS") is not True


def test_pytest_conn_max_age_zero():
    cfg = _config(
        {"TEST_DATABASE_URL": TEST_ONLY, "DATABASE_URL": DIRECT},
        running_pytest=True,
        direct_url=True,
    )
    assert cfg["CONN_MAX_AGE"] == 0


def test_run_daily_uses_direct_url():
    with patch.dict(os.environ, {"DATABASE_URL": DIRECT, "DATABASE_URL_POOLED": POOLED}, clear=True):
        with patch.object(settings, "_running_pytest", return_value=False):
            with patch("sys.argv", ["manage.py", "run_daily"]):
                cfg = settings._database_config()
    assert cfg["USER"] == "main"
    assert cfg.get("DISABLE_SERVER_SIDE_CURSORS") is not True


def test_migrate_uses_migrate_database_url():
    env = {
        "MIGRATE_DATABASE_URL": MIGRATE,
        "DATABASE_URL": DIRECT,
        "DATABASE_URL_POOLED": POOLED,
    }
    with patch.dict(os.environ, env, clear=True):
        with patch.object(settings, "_running_pytest", return_value=False):
            with patch("sys.argv", ["manage.py", "migrate"]):
                cfg = settings._database_config()
    assert cfg["USER"] == "owner"
    assert cfg["CONN_MAX_AGE"] == 0
    assert cfg.get("DISABLE_SERVER_SIDE_CURSORS") is not True


def test_migrate_missing_migrate_database_url_raises():
    env = {"DATABASE_URL": DIRECT, "DATABASE_URL_POOLED": POOLED}
    with patch.dict(os.environ, env, clear=True):
        with patch.object(settings, "_running_pytest", return_value=False):
            with patch("sys.argv", ["manage.py", "migrate"]):
                with pytest.raises(RuntimeError, match="MIGRATE_DATABASE_URL"):
                    settings._database_config()


def test_migrate_does_not_fall_back_to_database_url():
    env = {"DATABASE_URL": DIRECT, "DATABASE_URL_POOLED": POOLED}
    with patch.dict(os.environ, env, clear=True):
        with patch.object(settings, "_running_pytest", return_value=False):
            with patch("sys.argv", ["manage.py", "migrate", "--plan"]):
                with pytest.raises(RuntimeError, match="MIGRATE_DATABASE_URL"):
                    settings._database_config()


def test_process_email_outbox_uses_database_url():
    env = {
        "MIGRATE_DATABASE_URL": MIGRATE,
        "DATABASE_URL": DIRECT,
        "DATABASE_URL_POOLED": POOLED,
    }
    with patch.dict(os.environ, env, clear=True):
        with patch.object(settings, "_running_pytest", return_value=False):
            with patch("sys.argv", ["manage.py", "process_email_outbox"]):
                cfg = settings._database_config()
    assert cfg["USER"] == "main"


def test_gunicorn_uses_pooled_database_url():
    env = {
        "MIGRATE_DATABASE_URL": MIGRATE,
        "DATABASE_URL": DIRECT,
        "DATABASE_URL_POOLED": POOLED,
    }
    with patch.dict(os.environ, env, clear=True):
        with patch.object(settings, "_running_pytest", return_value=False):
            with patch("sys.argv", ["/usr/bin/gunicorn", "config.wsgi:application"]):
                cfg = settings._database_config()
    assert cfg["USER"] == "pool"
    assert cfg["DISABLE_SERVER_SIDE_CURSORS"] is True


def test_substring_migrate_in_later_arg_does_not_select_migrate_url():
    env = {
        "MIGRATE_DATABASE_URL": MIGRATE,
        "DATABASE_URL": DIRECT,
        "DATABASE_URL_POOLED": POOLED,
    }
    with patch.dict(os.environ, env, clear=True):
        with patch.object(settings, "_running_pytest", return_value=False):
            with patch("sys.argv", ["manage.py", "shell", "--command", "print('migrate')"]):
                cfg = settings._database_config()
    assert cfg["USER"] == "main"


def test_django_management_command_detection():
    assert settings._django_management_command() is None
    with patch("sys.argv", ["manage.py", "migrate"]):
        assert settings._django_management_command() == "migrate"
    with patch("sys.argv", ["manage.py", "migrate", "--noinput"]):
        assert settings._django_management_command() == "migrate"
    with patch("sys.argv", ["/opt/venv/bin/gunicorn", "config.wsgi:application"]):
        assert settings._django_management_command() is None


def test_django_admin_migrate_uses_migrate_database_url():
    env = {
        "MIGRATE_DATABASE_URL": MIGRATE,
        "DATABASE_URL": DIRECT,
        "DATABASE_URL_POOLED": POOLED,
    }
    with patch.dict(os.environ, env, clear=True):
        with patch.object(settings, "_running_pytest", return_value=False):
            with patch("sys.argv", ["django-admin", "migrate"]):
                cfg = settings._database_config()
    assert cfg["USER"] == "owner"


def test_manage_py_full_path_migrate_uses_migrate_database_url():
    env = {
        "MIGRATE_DATABASE_URL": MIGRATE,
        "DATABASE_URL": DIRECT,
        "DATABASE_URL_POOLED": POOLED,
    }
    with patch.dict(os.environ, env, clear=True):
        with patch.object(settings, "_running_pytest", return_value=False):
            with patch("sys.argv", ["/app/backend/manage.py", "migrate"]):
                cfg = settings._database_config()
    assert cfg["USER"] == "owner"


@pytest.mark.parametrize("command", ["makemigrations", "showmigrations"])
def test_migration_introspection_commands_use_database_url(command):
    env = {
        "MIGRATE_DATABASE_URL": MIGRATE,
        "DATABASE_URL": DIRECT,
        "DATABASE_URL_POOLED": POOLED,
    }
    with patch.dict(os.environ, env, clear=True):
        with patch.object(settings, "_running_pytest", return_value=False):
            with patch("sys.argv", ["manage.py", command]):
                cfg = settings._database_config()
    assert cfg["USER"] == "main"


def test_python_m_django_migrate_uses_pooled_not_migrate_url():
    """``python -m django`` is unsupported for migrate URL selection; use manage.py instead."""
    env = {
        "MIGRATE_DATABASE_URL": MIGRATE,
        "DATABASE_URL": DIRECT,
        "DATABASE_URL_POOLED": POOLED,
    }
    with patch.dict(os.environ, env, clear=True):
        with patch.object(settings, "_running_pytest", return_value=False):
            with patch("sys.argv", ["/usr/bin/python", "-m", "django", "migrate"]):
                cfg = settings._database_config()
    assert cfg["USER"] == "pool"
    assert cfg["DISABLE_SERVER_SIDE_CURSORS"] is True
