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
    ("postgresql_url_password", re.compile("postgresql" + r"://" + r"[^:]+:[^@\s]+@")),
    ("secret_key_literal", re.compile(r"(?i)(SECRET_KEY|API_KEY)\s*=\s*['\"][^'\"]{20,}['\"]")),
    ("jwt_literal", re.compile(r"\beyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b")),
    ("resend_key", re.compile(r"\bre_[a-zA-Z0-9_-]{20,}\b")),
    ("brevo_key", re.compile(r"\bxkeysib-[a-zA-Z0-9_-]{20,}\b")),
    ("stripe_sk", re.compile(r"\bsk_(live|test)_[a-zA-Z0-9]{16,}\b")),
]

FAKE_OK_SUBSTRINGS = (
    "fake-secret-key-change-me",
)

_NEON_FIXTURE_ACCOUNTS = (
    ("main", "mainpass"),
    ("pool", "poolpass"),
    ("testuser", "testpass"),
    ("owner", "ownerpass"),
)
_BREVO_FIXTURE_MARKERS = (
    "test-key-not-real",
    "deadbeef1234567890abcdefghij",
    "should-not-appear",
)


def _in_tests(rel: str) -> bool:
    return rel.replace("\\", "/").startswith("backend/tests/")


def _pg_credential_prefix(user: str, password: str) -> str:
    return "postgresql://" + user + ":" + password + "@"


def _postgresql_test_fixture(fragment: str) -> bool:
    if fragment.startswith(_pg_credential_prefix("user", "password")):
        return True
    if fragment.startswith(_pg_credential_prefix("user", "sekret")):
        return True
    return any(fragment == _pg_credential_prefix(user, pw) for user, pw in _NEON_FIXTURE_ACCOUNTS)


def _jwt_test_fixture(token: str) -> bool:
    parts = token.split(".")
    if len(parts) != 3 or not parts[0].startswith("eyJ"):
        return False
    # Masking tests use short placeholder payload/signature segments, not real JWT blobs.
    return len(parts[1]) <= 12 and len(parts[2]) <= 12


def _brevo_test_fixture(fragment: str) -> bool:
    return any(marker in fragment for marker in _BREVO_FIXTURE_MARKERS)


def _match_allowed(rule: str, matched: str, rel: str) -> bool:
    if rule in ("postgresql_url_password", "secret_key_literal"):
        if any(ok in matched for ok in FAKE_OK_SUBSTRINGS):
            return True
    if not _in_tests(rel):
        return False
    if rule == "postgresql_url_password":
        return _postgresql_test_fixture(matched)
    if rule == "jwt_literal":
        return _jwt_test_fixture(matched)
    if rule == "brevo_key":
        return _brevo_test_fixture(matched)
    return False


def secret_violations_in_text(rel: str, text: str) -> list[str]:
    """Return rule names that match at least one non-exempt secret pattern in text."""
    rel = rel.replace("\\", "/")
    hit_rules: list[str] = []
    for rule, pattern in RULES:
        unallowed = False
        for match in pattern.finditer(text):
            if not _match_allowed(rule, match.group(0), rel):
                unallowed = True
                break
        if unallowed:
            hit_rules.append(rule)
    return hit_rules


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
        for rule in secret_violations_in_text(rel, text):
            hits.append((rel, rule))
    return hits


def main() -> int:
    hits = scan()
    for path, rule in sorted(set(hits)):
        print(f"{path}\t{rule}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())