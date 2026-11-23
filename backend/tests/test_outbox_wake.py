"""Tests for post-commit debounced GitHub outbox wake dispatch."""

from __future__ import annotations

import concurrent.futures
import io
import json
import threading
import urllib.error
from unittest import mock

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.db import transaction
from django.test import override_settings

from core.mail_enqueue import enqueue_outbound_email
from core.models.outbound_email import OutboundEmailType
from core.outbox.wake import (
    WAKE_DEBOUNCE_CACHE_KEY,
    _on_commit_try_wake,
    cache_supports_cross_process_debounce,
    schedule_outbox_wake_after_commit,
)
from tests.outbox_helpers import run_pending_on_commit_hooks


def _minimal_wake_settings(**extra):
    base = {
        "OUTBOX_WAKE_DISPATCH_ENABLED": True,
        "OUTBOX_WAKE_GITHUB_TOKEN": "ghp_test_token",
        "OUTBOX_WAKE_GITHUB_OWNER": "test-owner",
        "OUTBOX_WAKE_GITHUB_REPO": "test-repo",
        "OUTBOX_WAKE_DEBOUNCE_SECONDS": 60,
        "OUTBOX_WAKE_HTTP_TIMEOUT_SECONDS": 2.0,
    }
    base.update(extra)
    return base


def _db_cache_settings():
    return {
        "CACHES": {
            "default": {
                "BACKEND": "django.core.cache.backends.db.DatabaseCache",
                "LOCATION": "ongsho_cache_test_wake",
            }
        }
    }


def _ensure_cache_table(table: str = "ongsho_cache_test_wake") -> None:
    call_command("createcachetable", table, verbosity=0)


@pytest.mark.django_db
def test_wake_disabled_by_default_no_http():
    with mock.patch("urllib.request.urlopen") as urlopen_mock:
        with transaction.atomic():
            enqueue_outbound_email(
                email_type=OutboundEmailType.ACCOUNT_VERIFY,
                business_event_id="wake-default-off",
                to_email="wake-default@example.com",
                payload={},
            )
        run_pending_on_commit_hooks()
        urlopen_mock.assert_not_called()


@pytest.mark.django_db
@override_settings(**_minimal_wake_settings(), CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "wake-locmem"}})
def test_locmem_cache_skips_dispatch(caplog):
    with mock.patch("urllib.request.urlopen") as urlopen_mock:
        with transaction.atomic():
            enqueue_outbound_email(
                email_type=OutboundEmailType.ACCOUNT_VERIFY,
                business_event_id="wake-locmem-skip",
                to_email="wake@example.com",
                payload={},
            )
        run_pending_on_commit_hooks()
        urlopen_mock.assert_not_called()


@pytest.mark.django_db
@override_settings(**_minimal_wake_settings(), **_db_cache_settings())
def test_rollback_never_dispatches():
    _ensure_cache_table()
    cache.clear()
    with mock.patch("urllib.request.urlopen") as urlopen_mock:
        try:
            with transaction.atomic():
                enqueue_outbound_email(
                    email_type=OutboundEmailType.ACCOUNT_VERIFY,
                    business_event_id="wake-rollback",
                    to_email="rollback@example.com",
                    payload={},
                )
                raise RuntimeError("force rollback")
        except RuntimeError:
            pass
        run_pending_on_commit_hooks()
        urlopen_mock.assert_not_called()


@pytest.mark.django_db
@override_settings(**_minimal_wake_settings(), **_db_cache_settings())
def test_commit_registers_single_dispatch_on_debounce_win():
    _ensure_cache_table()
    cache.clear()

    fake_response = mock.MagicMock()
    fake_response.status = 204
    fake_response.__enter__ = lambda s: s
    fake_response.__exit__ = mock.Mock(return_value=False)

    with mock.patch("urllib.request.urlopen", return_value=fake_response) as urlopen_mock:
        with transaction.atomic():
            enqueue_outbound_email(
                email_type=OutboundEmailType.ACCOUNT_VERIFY,
                business_event_id="wake-commit-1",
                to_email="a@example.com",
                payload={},
            )
            enqueue_outbound_email(
                email_type=OutboundEmailType.ACCOUNT_VERIFY,
                business_event_id="wake-commit-2",
                to_email="b@example.com",
                payload={},
            )
        run_pending_on_commit_hooks()
        assert urlopen_mock.call_count == 1
        request = urlopen_mock.call_args[0][0]
        body = json.loads(request.data.decode())
        assert body["inputs"]["outbox_wake"] == "true"
        assert body["ref"] == "main"


@pytest.mark.django_db
@override_settings(**_minimal_wake_settings(), **_db_cache_settings())
def test_duplicate_on_commit_hooks_coalesce_to_one_dispatch():
    _ensure_cache_table()
    cache.clear()
    fake_response = mock.MagicMock()
    fake_response.status = 204
    fake_response.__enter__ = lambda s: s
    fake_response.__exit__ = mock.Mock(return_value=False)

    with mock.patch("urllib.request.urlopen", return_value=fake_response) as urlopen_mock:
        with transaction.atomic():
            schedule_outbox_wake_after_commit()
            schedule_outbox_wake_after_commit()
            schedule_outbox_wake_after_commit()
        run_pending_on_commit_hooks()
        assert urlopen_mock.call_count == 1


@pytest.mark.django_db
@override_settings(**_minimal_wake_settings(), **_db_cache_settings())
def test_github_api_failure_does_not_raise():
    _ensure_cache_table()
    cache.clear()
    http_err = urllib.error.HTTPError(
        url="https://api.github.com",
        code=500,
        msg="err",
        hdrs=None,
        fp=io.BytesIO(b""),
    )
    with mock.patch("urllib.request.urlopen", side_effect=http_err):
        _on_commit_try_wake()


@pytest.mark.django_db
@override_settings(**_minimal_wake_settings(), **_db_cache_settings())
def test_github_timeout_does_not_raise():
    _ensure_cache_table()
    cache.clear()
    with mock.patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("timed out"),
    ):
        _on_commit_try_wake()


@pytest.mark.django_db
@override_settings(**_minimal_wake_settings(), **_db_cache_settings())
def test_cache_add_failure_logs_no_crash(caplog):
    with mock.patch("core.outbox.wake.cache.add", side_effect=RuntimeError("db down")):
        with mock.patch("urllib.request.urlopen") as urlopen_mock:
            _on_commit_try_wake()
            urlopen_mock.assert_not_called()


@pytest.mark.django_db
@override_settings(**_minimal_wake_settings(), **_db_cache_settings())
def test_concurrent_debounce_winner_at_most_one_dispatch():
    _ensure_cache_table()
    cache.clear()
    barrier = threading.Barrier(8)
    dispatches = threading.Semaphore(0)
    call_count = {"n": 0}
    lock = threading.Lock()

    fake_response = mock.MagicMock()
    fake_response.status = 204
    fake_response.__enter__ = lambda s: s
    fake_response.__exit__ = mock.Mock(return_value=False)

    def counting_urlopen(*args, **kwargs):
        with lock:
            call_count["n"] += 1
        dispatches.release()
        return fake_response

    def worker():
        barrier.wait()
        _on_commit_try_wake()

    with mock.patch("urllib.request.urlopen", side_effect=counting_urlopen):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futs = [pool.submit(worker) for _ in range(8)]
            concurrent.futures.wait(futs)
        assert call_count["n"] <= 1


@pytest.mark.django_db
@override_settings(**_minimal_wake_settings(), **_db_cache_settings())
def test_database_cache_backend_is_shared():
    assert cache_supports_cross_process_debounce() is True
    _ensure_cache_table()
    cache.clear()
    assert cache.add(WAKE_DEBOUNCE_CACHE_KEY, 1, 30) is True
    assert cache.add(WAKE_DEBOUNCE_CACHE_KEY, 1, 30) is False


@pytest.mark.django_db
def test_missing_github_config_skips_when_token_empty():
    with override_settings(
        **_minimal_wake_settings(OUTBOX_WAKE_GITHUB_TOKEN=""),
        **_db_cache_settings(),
    ):
        _ensure_cache_table()
        cache.clear()
        with mock.patch("urllib.request.urlopen") as urlopen_mock:
            _on_commit_try_wake()
            urlopen_mock.assert_not_called()


@pytest.mark.django_db
@override_settings(**_minimal_wake_settings(), **_db_cache_settings())
def test_bulk_style_enqueues_in_one_transaction_one_dispatch():
    _ensure_cache_table()
    cache.clear()
    fake_response = mock.MagicMock()
    fake_response.status = 204
    fake_response.__enter__ = lambda s: s
    fake_response.__exit__ = mock.Mock(return_value=False)

    with mock.patch("urllib.request.urlopen", return_value=fake_response) as urlopen_mock:
        with transaction.atomic():
            for i in range(5):
                enqueue_outbound_email(
                    email_type=OutboundEmailType.ACCOUNT_VERIFY,
                    business_event_id=f"bulk-wake-{i}",
                    to_email=f"user{i}@example.com",
                    payload={},
                )
        run_pending_on_commit_hooks()
        assert urlopen_mock.call_count == 1


def test_worker_advisory_lock_busy_is_independent_of_wake(db):
    """Wake only triggers GHA; local worker still no-ops when lock held (existing behavior)."""
    out = io.StringIO()
    with mock.patch(
        "core.management.commands.process_email_outbox.try_worker_lock",
        return_value=False,
    ):
        with mock.patch(
            "core.management.commands.process_email_outbox.run_worker_pass",
        ) as run_pass:
            call_command("process_email_outbox", stdout=out)
            run_pass.assert_not_called()
    assert "advisory_lock=busy" in out.getvalue()