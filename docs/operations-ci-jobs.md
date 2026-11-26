# Operations: CI, email outbox, and daily billing jobs

Stage **5.3** adds GitHub Actions **quality CI** (no production email or billing), improves **outbox** and **`run_daily`** observability, and introduces an **optional** daily scheduler workflow that remains **disabled by default**.

Passing tests and merging CI does **not** prove production scheduling or inbox delivery.

---

## 1. CI workflow (`.github/workflows/ci.yml`)

### Triggers

- `pull_request` → `main`
- `push` → `main`

### Jobs (suggested branch-protection checks)

| Job | What it proves |
|-----|----------------|
| `backend` | Full `pytest` on PostgreSQL 16, migration check, `manage.py check`, `scan_secrets.py` |
| `frontend` | `npm ci`, Vitest, ESLint, Vite build, `check:dist` |

**Not included:** email dispatch, `run_daily`, deploy, production secrets.

### Backend CI database

- Service container: `postgres:16-alpine`, database `test_ongsho`
- `DATABASE_URL=postgresql://ongsho:ci_test_only@localhost:5432/test_ongsho` (CI-only credentials)
- Locmem email backend and public test Fernet keys for invite delivery (same pattern as pytest defaults)

### Local parity

```bash
cd backend
python -m pytest
python manage.py makemigrations --check --dry-run
python manage.py check
python scripts/scan_secrets.py
```

```bash
cd frontend/webapp
npm ci
npm test
npm run lint
npm run build
npm run check:dist
```

---

## 2. Email outbox worker

### Production / GHA worker

Workflow: `.github/workflows/process-email-outbox.yml` (unchanged gates: `OUTBOX_WORKER_ENABLED`, schedule/manual/wake flags).

Command:

```bash
python manage.py process_email_outbox --batch-size 50 --max-runtime 55
```

### Safe operator output (no PII)

After a run, stdout is multi-line `key=value`:

```text
worker_id=host-abc12345
advisory_lock=acquired
duration_seconds=1.234
claimed=3
sent=2
retry=1
failed=0
cancelled=0
skipped_ownership=0
eligible_remaining=0
exit_ok=true
```

- **Row-level** `retry` / `failed` are normal; workflow exits **0** when processing completed without an operational exception.
- **Operational failure** (uncaught exception in worker pass) → `CommandError`, non-zero exit, `operational_error=…` in stdout.
- **Advisory lock busy** → `advisory_lock=busy … exit_ok=true` (exit 0).

A JSON line is also written to logs: `outbox_worker_run {…}` (counts only, no addresses or payloads).

### Read-only backlog inspection

```bash
python manage.py process_email_outbox --dry-run
```

Prints aggregate counts (`status_pending`, `status_retry`, `stale_processing_leases`, `eligible`, optional `backlog_by_type`, oldest backlog timestamps). **Does not** claim rows or send mail.

### At-least-once delivery caveat

If Brevo accepts a message and the worker crashes before marking `sent`, a **duplicate provider submit** is possible on retry. This is documented in `core/outbox/worker.py`; observability does not change that model.

---

## 3. Daily billing job (`run_daily`)

### Command

```bash
python manage.py run_daily
python manage.py run_daily --date=2026-11-25
```

Uses advisory lock **`86420101`** (distinct from outbox `86420102`).

### Operator stdout

```text
run_date=2026-11-25 lock_acquired=true success=true duration_seconds=2.345 …
steps=members_closed,expired,trials_activated,generate_charges,lock_charges,ensure_dues,send_reminders
```

Lock busy:

```text
run_date=2026-11-25 lock_acquired=false skipped_due_to_lock=true … exit=0
```

Step failure: `success=false`, `failed_step=…`, `error_type=…`, command exits **non-zero**.

Structured JSON is logged (counts and step names only).

### Alternative GHA scheduler (disabled by default)

File: `.github/workflows/run-daily-job.yml`

**Enabled only when** repository variable `RUN_DAILY_JOB_ENABLED` == `true` **and** (cron schedule **or** manual `confirm_live_processing`).

**Before enabling:** confirm whether Render (or another host) already runs `run_daily`. Do not run two production schedulers.

Requires same production secrets as the outbox worker for DB access (`SECRET_KEY`, `DATABASE_URL`, etc.) — set only in GitHub, never in YAML values.

---

## 4. GitHub configuration (names only)

### CI

No repository secrets required for `ci.yml` (test-only env in workflow).

### Outbox worker (existing)

**Secrets:** `SECRET_KEY`, `DATABASE_URL`, `BREVO_API_KEY`, `INVITE_DELIVERY_ENCRYPTION_KEYS`  
**Variables:** `OUTBOX_WORKER_ENABLED`, `OUTBOX_SCHEDULE_ENABLED`, `OUTBOX_WAKE_ENABLED`, plus Django/app tunables (see `EMAIL_OUTBOX_WORKER_RUNBOOK.md`).

### Daily job (optional)

**Variable:** `RUN_DAILY_JOB_ENABLED` (default off)  
**Secrets:** same DB/Django secrets as worker when enabled.

---

## 5. Recovery

| Situation | Action |
|-----------|--------|
| Outbox backlog | `process_email_outbox --dry-run`, then inspect `FAILED` / `RETRY` in DB admin (read-only); fix root cause; rely on retry or manual ops |
| Worker lock busy | Expected under overlap; wait for lease / next cron |
| `run_daily` lock busy | Another instance holds `86420101`; do not start a second concurrent run |
| Partial `run_daily` | Check stdout `failed_step`; fix cause; re-run same date (billing/reminders are idempotent by design; re-run charges should not duplicate periods) |