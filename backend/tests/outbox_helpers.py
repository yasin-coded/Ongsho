"""Test helpers for transactional outbox → locmem mail delivery."""

from __future__ import annotations

from django.db import connection

from core.outbox.worker import run_worker_pass


def run_pending_on_commit_hooks() -> None:
    """
    Execute pending transaction.on_commit callbacks under pytest-django.

    Pytest-django keeps the database connection inside an outer atomic block, so
    production commit hooks never fire on their own during tests. This helper runs
    queued callbacks the same way a real outer commit would (test-only).
    """
    if connection.in_atomic_block:
        pending = list(connection.run_on_commit)
        connection.run_on_commit = []
        for _sids, func, robust in pending:
            if robust:
                try:
                    func()
                except Exception:
                    name = getattr(func, "__qualname__", func)
                    import logging

                    logging.getLogger(__name__).exception(
                        "on_commit test hook failed callback=%s",
                        name,
                    )
            else:
                func()
        return
    connection.run_and_clear_commit_hooks()


def flush_outbound_to_mailbox(*, worker_id: str = "pytest-mail-flush") -> None:
    """Drain pending OutboundEmail rows through the worker into locmem mail.outbox."""
    run_worker_pass(batch_size=200, worker_id=worker_id, max_runtime_seconds=120.0)