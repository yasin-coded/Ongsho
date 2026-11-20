"""Run callables in parallel threads (for race tests)."""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence

from django.db import connections
from django.db import transaction as db_transaction


def run_concurrently(*fns: Callable[[], object] | Sequence[Callable[[], object]], transaction: bool = False):
    """
    Run callables in parallel. Returns ``(results, exceptions)`` aligned with callables.

    Accepts either ``run_concurrently(fn1, fn2, ...)`` or ``run_concurrently([fn1, fn2])``.
    When ``transaction`` is True, each worker runs inside ``transaction.atomic()`` and
    closes DB connections in ``finally`` (use with ``django_db(transaction=True)``).
    """
    if len(fns) == 1 and not callable(fns[0]):
        callables = list(fns[0])
    else:
        callables = [fn for fn in fns if callable(fn)]
    n = len(callables)
    results: list = [None] * n
    exceptions: list[BaseException | None] = [None] * n

    def worker(index: int, fn: Callable[[], object]):
        def run():
            try:
                if transaction:
                    with db_transaction.atomic():
                        results[index] = fn()
                else:
                    results[index] = fn()
            except BaseException as exc:  # noqa: BLE001
                exceptions[index] = exc
            finally:
                connections.close_all()

        return run

    threads = [threading.Thread(target=worker(i, fn)) for i, fn in enumerate(callables)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    connections.close_all()
    return results, exceptions