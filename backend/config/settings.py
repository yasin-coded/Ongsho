"""
Django settings for Ongsho. Environment variables are loaded with python-dotenv from:

1. Repository root `.env` (parent of `backend/`) — typical for shared Neon URLs
2. `backend/.env` if present (overrides root for local-only values)
"""

import json
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
    os.environ.setdefault("CACHE_BACKEND", "locmem")
    os.environ.setdefault("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")


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


def _running_pytest() -> bool:
    if "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    if sys.argv and "pytest" in Path(sys.argv[0]).name:
        return True
    return False


if _running_pytest():
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


def _use_direct_database_url() -> bool:
    if _running_pytest():
        return True
    management_cmds = {
        "migrate",
        "makemigrations",
        "showmigrations",
        "createsuperuser",
        "test",
        "flush",
        "sqlmigrate",
        "squashmigrations",
    }
    return any(cmd in sys.argv for cmd in management_cmds)


def _database_config() -> dict:
    if _running_pytest():
        test_url = os.environ.get("TEST_DATABASE_URL")
        if test_url:
            return dj_database_url.parse(test_url, conn_max_age=0)
    if _use_direct_database_url():
        url_var = "DATABASE_URL"
    else:
        url_var = "DATABASE_URL_POOLED"
    url = os.environ.get(url_var)
    if not url:
        raise RuntimeError(f"Missing required environment variable: {url_var}")
    config = dj_database_url.parse(url, conn_max_age=0)
    if url_var == "DATABASE_URL_POOLED":
        # Top-level Django setting (not a libpq connect kwarg); required for PgBouncer transaction mode.
        config["DISABLE_SERVER_SIDE_CURSORS"] = True
    return config


SECRET_KEY = os.environ["SECRET_KEY"]
DEBUG = _env_bool("DEBUG")
ALLOWED_HOSTS = _env_list("ALLOWED_HOSTS")
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
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.logging.RequestLogMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
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

STATIC_URL = "static/"

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PAGINATION_CLASS": "core.pagination.OngshoPageNumberPagination",
    "PAGE_SIZE": 25,
    "EXCEPTION_HANDLER": "core.exceptions.ongsho_exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = _env_str("DEFAULT_FROM_EMAIL")
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
        "jobs.services": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
