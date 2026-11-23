"""
Post-commit debounced GitHub Actions workflow_dispatch to wake the email outbox worker.

Wake dispatch is best-effort: committed rows remain in PostgreSQL if GitHub is unavailable.
Scheduled GHA recovery remains the backstop.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from django.conf import settings
from django.core.cache import cache
from django.db import transaction

logger = logging.getLogger(__name__)

WAKE_DEBOUNCE_CACHE_KEY = "ongsho:outbox:wake:debounce"


def cache_supports_cross_process_debounce() -> bool:
    """DatabaseCache is shared across Gunicorn workers via PostgreSQL; LocMem is not."""
    backend = settings.CACHES.get("default", {}).get("BACKEND", "")
    return backend == "django.core.cache.backends.db.DatabaseCache"


def schedule_outbox_wake_after_commit() -> None:
    """Register a post-commit wake attempt (no-op until outer transaction commits)."""
    transaction.on_commit(_on_commit_try_wake, robust=True)


def _wake_dispatch_configured() -> bool:
    if not settings.OUTBOX_WAKE_DISPATCH_ENABLED:
        return False
    return bool(
        settings.OUTBOX_WAKE_GITHUB_TOKEN
        and settings.OUTBOX_WAKE_GITHUB_OWNER
        and settings.OUTBOX_WAKE_GITHUB_REPO
    )


def _on_commit_try_wake() -> None:
    if not _wake_dispatch_configured():
        return

    if not cache_supports_cross_process_debounce():
        logger.warning(
            "outbox_wake_skipped reason=non_shared_cache backend=%s",
            settings.CACHES.get("default", {}).get("BACKEND", ""),
        )
        return

    debounce_seconds = settings.OUTBOX_WAKE_DEBOUNCE_SECONDS
    try:
        won_debounce = cache.add(WAKE_DEBOUNCE_CACHE_KEY, 1, timeout=debounce_seconds)
    except Exception:
        logger.exception("outbox_wake_cache_add_failed")
        return

    if not won_debounce:
        logger.debug("outbox_wake_debounce_skip")
        return

    correlation_id = uuid.uuid4().hex
    _dispatch_github_workflow(correlation_id=correlation_id)


def _workflow_dispatch_url() -> str:
    owner = settings.OUTBOX_WAKE_GITHUB_OWNER
    repo = settings.OUTBOX_WAKE_GITHUB_REPO
    workflow = settings.OUTBOX_WAKE_WORKFLOW_FILE
    return f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow}/dispatches"


def _dispatch_github_workflow(*, correlation_id: str) -> None:
    payload: dict[str, Any] = {
        "ref": settings.OUTBOX_WAKE_GITHUB_REF,
        "inputs": {
            "outbox_wake": "true",
        },
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib_request.Request(
        _workflow_dispatch_url(),
        data=data,
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {settings.OUTBOX_WAKE_GITHUB_TOKEN}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    timeout = settings.OUTBOX_WAKE_HTTP_TIMEOUT_SECONDS
    try:
        with urllib_request.urlopen(request, timeout=timeout) as response:
            status = int(response.status)
    except urllib_error.HTTPError as exc:
        status = int(exc.code)
    except (urllib_error.URLError, TimeoutError, OSError) as exc:
        logger.warning(
            "outbox_wake_dispatch_failed correlation_id=%s reason=%s",
            correlation_id,
            type(exc).__name__,
        )
        return

    if status in (204, 201):
        logger.info(
            "outbox_wake_dispatch_accepted correlation_id=%s status=%s",
            correlation_id,
            status,
        )
    else:
        logger.warning(
            "outbox_wake_dispatch_rejected correlation_id=%s status=%s",
            correlation_id,
            status,
        )