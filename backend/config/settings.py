"""
Django settings for Ongsho. Environment variables are loaded with python-dotenv from:

1. Repository root `.env` (parent of `backend/`) — typical for shared Neon URLs
2. `backend/.env` if present (overrides root for local-only values)
"""

import json
import math
import os
import sys
from datetime import timedelta
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent

load_dotenv(REPO_ROOT / ".env")
load_dotenv(BASE_DIR / ".env", override=True)

# Pytest bootstraps Django before conftest runs; supply non-secret defaults only for test runs.
if "pytest" in sys.argv[0] or any(arg == "pytest" or arg.endswith("pytest") for arg in sys.argv):
    os.environ.setdefault("DEFAULT_FROM_EMAIL", "Ongsho <test@example.com>")
    os.environ.setdefault("FRONTEND_BASE_URL", "http://localhost:5173")
    os.environ.setdefault("REFRESH_COOKIE_SECURE", "False")
    os.environ.setdefault("REFRESH_COOKIE_SAMESITE", "Lax")
    os.environ.setdefault("FRONTEND_ORIGINS", "http://localhost:5173")
    os.environ.setdefault("CSRF_TRUSTED_ORIGINS", "http://localhost:5173")
    os.environ.setdefault("CACHE_BACKEND", "locmem")
    os.environ.setdefault("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
    os.environ.setdefault("ADMIN_ENABLED", "True")
    os.environ.setdefault("ADMIN_URL", "admin/")
    os.environ.setdefault("SECURE_SSL_REDIRECT", "False")
    os.environ.setdefault("TRUST_PROXY_SSL", "False")
    from core.test_support.invite_delivery_keys import apply_test_invite_delivery_encryption_env

    apply_test_invite_delivery_encryption_env()


def _env_bool(name: str) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_list(name: str) -> list[str]:
    raw = os.environ.get(name)
    if raw is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return [part.strip() for part in raw.split(",") if part.strip()]


def _env_str(name: str) -> str:
    raw = os.environ.get(name)
    if raw is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return raw.strip()


def _env_bool_default(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_str_default(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip()


def _positive_int_env(name: str, default: str) -> int:
    raw = os.environ.get(name, default)
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive integer")
    return value


def _load_invite_delivery_encryption_keys() -> dict[int, str]:
    from core.crypto.invite_delivery import parse_invite_delivery_encryption_keys_json

    raw = os.environ.get("INVITE_DELIVERY_ENCRYPTION_KEYS", "").strip()
    if not raw:
        return {}
    return parse_invite_delivery_encryption_keys_json(raw)


def _load_invite_delivery_encryption_active_version(keys: dict[int, str]) -> int:
    raw = os.environ.get("INVITE_DELIVERY_ENCRYPTION_ACTIVE_VERSION", "1").strip()
    try:
        version = int(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("INVITE_DELIVERY_ENCRYPTION_ACTIVE_VERSION must be an integer") from exc
    if version < 1:
        raise RuntimeError("INVITE_DELIVERY_ENCRYPTION_ACTIVE_VERSION must be >= 1")
    if keys and version not in keys:
        raise RuntimeError(
            f"INVITE_DELIVERY_ENCRYPTION_ACTIVE_VERSION {version} is not present in INVITE_DELIVERY_ENCRYPTION_KEYS"
        )
    return version


def _brevo_api_timeout() -> float:
    raw = os.environ.get("BREVO_API_TIMEOUT", "10")
    try:
        timeout = float(str(raw).strip())
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            "BREVO_API_TIMEOUT must be a number of seconds (positive and finite)."
        ) from exc
    if not math.isfinite(timeout) or timeout <= 0:
        raise RuntimeError(
            "BREVO_API_TIMEOUT must be a positive finite number of seconds."
        )
    return timeout


def _running_pytest() -> bool:
    if "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    if sys.argv and "pytest" in Path(sys.argv[0]).name:
        return True
    return False


if _running_pytest():
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


def _first_management_command_arg(argv_tail: list[str]) -> str | None:
    for arg in argv_tail:
        if arg.startswith("-"):
            continue
        return arg
    return None


def _django_management_command() -> str | None:
    """Return the Django management subcommand name, or None for WSGI/cron runtimes.

    Recognized entrypoints: ``manage.py`` / ``django-admin`` only. ``python -m django`` is not
    supported for database URL selection (use ``manage.py`` or ``django-admin``).
    """
    if not sys.argv:
        return None
    program = Path(sys.argv[0]).name
    if program in ("django-admin", "django-admin.py") or program.endswith("manage.py"):
        return _first_management_command_arg(sys.argv[1:])
    return None


_DIRECT_DATABASE_COMMANDS = frozenset(
    {
        "migrate",
        "makemigrations",
        "showmigrations",
        "createsuperuser",
        "test",
        "flush",
        "sqlmigrate",
        "squashmigrations",
        "run_daily",
        "process_email_outbox",
        "seed_perf",
        "shell",
        "dbshell",
    }
)


def _use_direct_database_url() -> bool:
    if _running_pytest():
        return True
    cmd = _django_management_command()
    return cmd in _DIRECT_DATABASE_COMMANDS if cmd else False


def _db_conn_max_age(*, pooled_runtime: bool) -> int:
    if not pooled_runtime:
        return 0
    raw = os.environ.get("DB_CONN_MAX_AGE", "60")
    return int(raw.strip())


def _database_config() -> dict:
    if _running_pytest():
        test_url = os.environ.get("TEST_DATABASE_URL")
        if test_url:
            return dj_database_url.parse(test_url, conn_max_age=0)
    pooled_runtime = not _use_direct_database_url()
    management_cmd = _django_management_command()
    if management_cmd == "migrate":
        url_var = "MIGRATE_DATABASE_URL"
    elif _use_direct_database_url():
        url_var = "DATABASE_URL"
    else:
        url_var = "DATABASE_URL_POOLED"
    url = os.environ.get(url_var)
    if not url:
        raise RuntimeError(f"Missing required environment variable: {url_var}")
    max_age = _db_conn_max_age(pooled_runtime=pooled_runtime)
    config = dj_database_url.parse(url, conn_max_age=max_age)
    if max_age > 0:
        config["CONN_HEALTH_CHECKS"] = True
    if url_var == "DATABASE_URL_POOLED":
        # Top-level Django setting (not a libpq connect kwarg); required for PgBouncer transaction mode.
        config["DISABLE_SERVER_SIDE_CURSORS"] = True
    return config


SECRET_KEY = os.environ["SECRET_KEY"]
DEBUG = _env_bool("DEBUG")
ALLOWED_HOSTS = _env_list("ALLOWED_HOSTS")
ADMIN_ENABLED = _env_bool_default("ADMIN_ENABLED", True)
_admin_raw = _env_str_default("ADMIN_URL", "admin/").strip("/")
ADMIN_URL = f"{_admin_raw}/" if _admin_raw else "admin/"

if DEBUG:
    CSRF_TRUSTED_ORIGINS = _env_list("CSRF_TRUSTED_ORIGINS") if os.environ.get("CSRF_TRUSTED_ORIGINS") else []
else:
    CSRF_TRUSTED_ORIGINS = _env_list("CSRF_TRUSTED_ORIGINS")
if _running_pytest() and "testserver" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS = [*ALLOWED_HOSTS, "testserver"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.postgres",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "core",
    "accounts",
    "catalog",
    "plans",
    "billing.apps.BillingConfig",
    "sharing",
    "dues",
    "payments",
    "notifications",
    "reports",
    "audit",
    "jobs",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.logging.RequestLogMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.ApiSecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {"default": _database_config()}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Dhaka"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

def apply_production_rest_framework(config: dict, *, debug: bool) -> dict:
    if debug:
        return config
    return {
        **config,
        "DEFAULT_RENDERER_CLASSES": [
            "rest_framework.renderers.JSONRenderer",
        ],
        "DEFAULT_PARSER_CLASSES": [
            "rest_framework.parsers.JSONParser",
        ],
    }


_REST_FRAMEWORK_BASE = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "accounts.authentication.ActiveUserJWTAuthentication",
    ],
    "DEFAULT_PAGINATION_CLASS": "core.pagination.OngshoPageNumberPagination",
    "PAGE_SIZE": 25,
    "EXCEPTION_HANDLER": "core.exceptions.ongsho_exception_handler",
}
REST_FRAMEWORK = apply_production_rest_framework(_REST_FRAMEWORK_BASE, debug=DEBUG)

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = _env_str("DEFAULT_FROM_EMAIL")
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "").strip()
BREVO_API_TIMEOUT = _brevo_api_timeout()

INVITE_DELIVERY_ENCRYPTION_KEYS = _load_invite_delivery_encryption_keys()
INVITE_DELIVERY_ENCRYPTION_ACTIVE_VERSION = _load_invite_delivery_encryption_active_version(
    INVITE_DELIVERY_ENCRYPTION_KEYS
)
if not INVITE_DELIVERY_ENCRYPTION_KEYS and not _running_pytest() and not DEBUG:
    raise RuntimeError("Missing INVITE_DELIVERY_ENCRYPTION_KEYS (required when DEBUG is False)")

OUTBOX_LEASE_SECONDS = _positive_int_env("OUTBOX_LEASE_SECONDS", "900")
# Worker retries are bounded; delivery is not guaranteed eventual (at-least-once attempts only).
OUTBOUND_EMAIL_MAX_ATTEMPTS = _positive_int_env("OUTBOUND_EMAIL_MAX_ATTEMPTS", "8")

# Post-commit GitHub workflow_dispatch wake (Render only); GitHub gate is OUTBOX_WAKE_ENABLED (repo var).
OUTBOX_WAKE_DISPATCH_ENABLED = _env_bool_default("OUTBOX_WAKE_DISPATCH_ENABLED", False)
OUTBOX_WAKE_DEBOUNCE_SECONDS = _positive_int_env("OUTBOX_WAKE_DEBOUNCE_SECONDS", "60")
OUTBOX_WAKE_GITHUB_TOKEN = os.environ.get("OUTBOX_WAKE_GITHUB_TOKEN", "").strip()
OUTBOX_WAKE_GITHUB_OWNER = _env_str_default("OUTBOX_WAKE_GITHUB_OWNER", "")
OUTBOX_WAKE_GITHUB_REPO = _env_str_default("OUTBOX_WAKE_GITHUB_REPO", "")
OUTBOX_WAKE_WORKFLOW_FILE = _env_str_default("OUTBOX_WAKE_WORKFLOW_FILE", "process-email-outbox.yml")
OUTBOX_WAKE_GITHUB_REF = _env_str_default("OUTBOX_WAKE_GITHUB_REF", "main")
_raw_wake_timeout = os.environ.get("OUTBOX_WAKE_HTTP_TIMEOUT_SECONDS", "3").strip()
try:
    _wake_timeout = float(_raw_wake_timeout)
except (TypeError, ValueError) as exc:
    raise RuntimeError("OUTBOX_WAKE_HTTP_TIMEOUT_SECONDS must be a positive number") from exc
if not math.isfinite(_wake_timeout) or _wake_timeout <= 0:
    raise RuntimeError("OUTBOX_WAKE_HTTP_TIMEOUT_SECONDS must be a positive finite number")
OUTBOX_WAKE_HTTP_TIMEOUT_SECONDS = _wake_timeout

FRONTEND_BASE_URL = _env_str("FRONTEND_BASE_URL").rstrip("/")
REFRESH_COOKIE_SECURE = _env_bool("REFRESH_COOKIE_SECURE")
REFRESH_COOKIE_SAMESITE = _env_str("REFRESH_COOKIE_SAMESITE")

INVITE_DAYS = int(os.environ.get("INVITE_DAYS", "7"))

EMAIL_VERIFY_MAX_AGE = timedelta(days=3)
PASSWORD_RESET_TIMEOUT = 3600

CORS_URLS_REGEX = r"^/api/.*$"
CORS_ALLOWED_ORIGINS = _env_list("FRONTEND_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
CORS_EXPOSE_HEADERS = ["Content-Disposition", "X-Statement-Number", "X-Request-ID"]

NUM_PROXIES = int(os.environ.get("NUM_PROXIES", "0"))
# Temporary: enable IP chain logging on /api/health/ when set + matching X-IP-Diagnostics-Token header.
IP_DIAGNOSTICS_TOKEN = os.environ.get("IP_DIAGNOSTICS_TOKEN", "").strip()

DEFAULT_THROTTLE_RATES = {
    "login_ip": "10/m",
    "login_email": "10/15m",
    "register_ip": "10/h",
    "password_reset_request_ip": "5/h",
    "password_reset_request_email": "3/h",
    "password_reset_confirm_ip": "10/h",
    "verify_email_ip": "20/h",
    "resend_verification_ip": "5/h",
    "resend_verification_email": "3/h",
    "refresh_ip": "60/m",
    "public_invite_get_ip": "60/m",
    "plan_join_get_ip": "60/m",
    "plan_join_signup_ip": "10/h",
    "invite_signup_ip": "10/h",
    "invite_create_user": "30/h",
    "invite_replace_user": "30/h",
    "payment_submit_user": "30/h",
    "statement_download_user": "30/h",
}

_throttle_overrides = json.loads(os.environ.get("THROTTLE_RATES", "{}") or "{}")
THROTTLE_RATES = {**DEFAULT_THROTTLE_RATES, **_throttle_overrides}

_cache_backend = os.environ.get("CACHE_BACKEND", "locmem").strip().lower()
_cache_table = os.environ.get("CACHE_TABLE", "ongsho_cache")
if _cache_backend == "db":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": _cache_table,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "ongsho-locmem",
        }
    }

SLOW_REQUEST_MS = int(os.environ.get("SLOW_REQUEST_MS", "800"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "mask_sensitive": {
            "()": "core.logging.SensitiveDataFilter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["mask_sensitive"],
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.environ.get("LOG_LEVEL", "INFO"),
    },
    "loggers": {
        "ongsho.request": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "ongsho.ip_diag": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "jobs.services": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

DATA_UPLOAD_MAX_MEMORY_SIZE = 1_048_576

if not DEBUG:
    SECURE_SSL_REDIRECT = _env_bool_default("SECURE_SSL_REDIRECT", True)
    SECURE_HSTS_SECONDS = 31_536_000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_REFERRER_POLICY = "same-origin"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    if _env_bool_default("TRUST_PROXY_SSL", False):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
