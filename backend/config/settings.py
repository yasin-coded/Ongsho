"""
Django settings for Ongsho. Environment variables are loaded with python-dotenv from:

1. Repository root `.env` (parent of `backend/`) — typical for shared Neon URLs
2. `backend/.env` if present (overrides root for local-only values)
"""

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


def _use_direct_database_url() -> bool:
    if "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    if sys.argv and "pytest" in Path(sys.argv[0]).name:
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

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.postgres",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "core",
    "accounts",
    "catalog",
    "plans",
    "billing",
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
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}
