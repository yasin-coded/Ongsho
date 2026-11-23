from __future__ import annotations

import importlib.util
from pathlib import Path


def test_gunicorn_conf_reads_env(monkeypatch):
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setenv("WEB_CONCURRENCY", "3")
    monkeypatch.setenv("WEB_THREADS", "8")
    path = Path(__file__).resolve().parents[1] / "gunicorn.conf.py"
    spec = importlib.util.spec_from_file_location("gunicorn_conf_test", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    assert mod.bind == "0.0.0.0:9000"
    assert mod.workers == 3
    assert mod.threads == 8
    assert mod.worker_class == "gthread"
    assert mod.preload_app is False
    assert mod.accesslog is None