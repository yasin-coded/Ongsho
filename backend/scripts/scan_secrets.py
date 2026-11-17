#!/usr/bin/env python3
"""Scan tracked files for accidental secrets (stdout: file + rule only, never matched text)."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent

ALLOWLIST_PATHS = frozenset(
    {
        "backend/.env.example",
        ".env.example",
    }
)

RULES: list[tuple[str, re.Pattern[str]]] = [
    ("private_key_header", re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("postgresql_url_password", re.compile(r"postgresql://[^:]+:[^@\s]+@")),
    ("secret_key_literal", re.compile(r"(?i)(SECRET_KEY|API_KEY)\s*=\s*['\"][^'\"]{20,}['\"]")),
    ("jwt_literal", re.compile(r"\beyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b")),
    ("resend_key", re.compile(r"\bre_[a-zA-Z0-9_-]{20,}\b")),
    ("brevo_key", re.compile(r"\bxkeysib-[a-zA-Z0-9_-]{20,}\b")),
    ("stripe_sk", re.compile(r"\bsk_(live|test)_[a-zA-Z0-9]{16,}\b")),
]

FAKE_OK = (
    "fake-secret-key-change-me",
    "postgresql://user:password@",
)


def _git_ls_files() -> list[str]:
    try:
        out = subprocess.check_output(["git", "ls-files"], cwd=REPO, text=True, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _walk_py_fallback() -> list[str]:
    paths = []
    for p in BACKEND.rglob("*.py"):
        rel = p.relative_to(REPO).as_posix()
        if "/tests/" in rel or "/migrations/" in rel or "__pycache__" in rel:
            continue
        paths.append(rel)
    return paths


def scan() -> list[tuple[str, str]]:
    files = _git_ls_files() or _walk_py_fallback()
    hits: list[tuple[str, str]] = []
    for rel in files:
        rel = rel.replace("\\", "/")
        if not rel.startswith("backend/"):
            continue
        if rel in ALLOWLIST_PATHS:
            continue
        path = REPO / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for rule, pattern in RULES:
            if not pattern.search(text):
                continue
            if any(ok in text for ok in FAKE_OK) and rule in ("postgresql_url_password", "secret_key_literal"):
                continue
            hits.append((rel.replace("\\", "/"), rule))
    return hits


def main() -> int:
    hits = scan()
    for path, rule in sorted(set(hits)):
        print(f"{path}\t{rule}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())