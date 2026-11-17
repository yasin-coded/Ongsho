"""Guards for dev-only database tooling (seed_perf, explain_hot_queries)."""

from __future__ import annotations

import os
import sys

from django.conf import settings
from django.core.management.base import CommandError

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", ""})


def _database_host() -> str:
    default = settings.DATABASES.get("default") or {}
    return (default.get("HOST") or "").strip().lower()


def _is_sqlite() -> bool:
    engine = (settings.DATABASES.get("default") or {}).get("ENGINE", "")
    return "sqlite" in engine


def assert_local_dev_database(tool_name: str) -> None:
    if not settings.DEBUG:
        raise CommandError(f"{tool_name} refuses to run unless DEBUG is True.")
    if os.environ.get("ALLOW_SEED_PERF_REMOTE", "").strip() == "1":
        return
    if _is_sqlite():
        return
    host = _database_host()
    if host not in _LOCAL_HOSTS:
        raise CommandError(
            f"{tool_name} refuses to run against database host {host!r}. "
            "Set ALLOW_SEED_PERF_REMOTE=1 to override."
        )


def assert_local_dev_database_or_exit(tool_name: str) -> None:
    try:
        assert_local_dev_database(tool_name)
    except CommandError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc