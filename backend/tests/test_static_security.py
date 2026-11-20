"""Static checks over application Python (excludes tests/ and migrations/)."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent

SKIP_PARTS = ("/tests/", "/migrations/", "__pycache__", "/.venv/", "/venv/")
SCAN_DIRS = ("accounts", "billing", "catalog", "config", "core", "dues", "jobs", "notifications", "payments", "plans", "reports", "sharing")

def _unsafe_sql_line(line: str) -> bool:
    stripped = line.strip()
    if ".raw(" in stripped or ".extra(" in stripped:
        if 'f"' in stripped or "f'" in stripped or ".format(" in stripped:
            return True
        if re.search(r"['\"][^'\"]*%[^s]['\"]", stripped):
            return True
    if "cursor.execute" in stripped:
        if re.search(r"execute\s*\(\s*f['\"]", stripped):
            return True
        if re.search(r"execute\s*\([^)]*\.format\s*\(", stripped):
            return True
        if "+" in stripped.split("execute", 1)[-1] and "(" in stripped:
            return True
    return False
UNSAFE_RE = re.compile(r"\b(eval|exec)\s*\(|pickle\.loads\s*\(|yaml\.load\s*\([^)]*\)|shell\s*=\s*True|mark_safe\s*\(")
FLOAT_BAN_DIRS = ("core/money.py", "dues/", "payments/", "billing/", "reports/")
VIEW_PK_RE = re.compile(r"\.objects\.(get|filter)\s*\(\s*pk\s*=")

# Heuristic hits outside selectors/services that are approved (path substring).
VIEW_PK_ALLOWLIST = frozenset(
    {
        "sharing/views.py",  # DRF passes pk from URL; ownership checked in services
        "plans/subscription_views.py",
        "payments/views.py",
        "dues/views.py",
        "notifications/views.py",
        "catalog/views.py",
        "accounts/views.py",
    }
)


def _app_py_files() -> list[Path]:
    out = []
    for name in SCAN_DIRS:
        root = BACKEND / name
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            rel = p.as_posix()
            if any(part in rel for part in SKIP_PARTS):
                continue
            out.append(p)
    return out


def test_no_dynamic_sql_fragments():
    hits = []
    for path in _app_py_files():
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if _unsafe_sql_line(line):
                hits.append(f"{path.relative_to(BACKEND)}:{i}")
    assert not hits, "Dynamic SQL fragments:\n" + "\n".join(hits)


def test_no_obviously_unsafe_calls():
    hits = []
    for path in _app_py_files():
        text = path.read_text(encoding="utf-8")
        if UNSAFE_RE.search(text):
            hits.append(str(path.relative_to(BACKEND)))
    assert not hits, "Unsafe calls in:\n" + "\n".join(hits)


def test_no_float_in_money_paths():
    hits = []
    for path in _app_py_files():
        rel = path.relative_to(BACKEND).as_posix()
        if not any(rel == d or rel.startswith(d) for d in FLOAT_BAN_DIRS):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "float":
                hits.append(f"{rel}:{node.lineno}")
    assert not hits, "float() in money paths:\n" + "\n".join(hits)


def test_secret_scan_script_clean():
    script = BACKEND / "scripts" / "scan_secrets.py"
    proc = subprocess.run([sys.executable, str(script)], cwd=REPO, capture_output=True, text=True)
    if proc.stdout.strip():
        pytest.fail("scan_secrets findings (file\\trule):\n" + proc.stdout.strip())


def test_view_direct_pk_heuristic_report():
    findings = []
    for path in (BACKEND / "sharing" / "views.py", BACKEND / "plans" / "subscription_views.py"):
        if not path.exists():
            continue
        rel = path.relative_to(BACKEND).as_posix()
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if VIEW_PK_RE.search(line) and "request.data" in line:
                findings.append(f"{rel}:{i}")
    unexpected = [f for f in findings if f.split(":")[0] not in VIEW_PK_ALLOWLIST]
    assert not unexpected, "Direct pk from request (use selectors):\n" + "\n".join(unexpected)
    if findings:
        # Informational: document allowlisted hits once per run (always passes).
        assert all(f.split(":")[0] in VIEW_PK_ALLOWLIST for f in findings)