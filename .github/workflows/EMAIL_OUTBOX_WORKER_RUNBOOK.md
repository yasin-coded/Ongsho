# Email outbox worker — production operations

Operations guide for the GitHub Actions worker defined in `process-email-outbox.yml`. It runs `python manage.py process_email_outbox` against the production Neon database and may send real transactional email via Brevo.

For local tuning defaults, see `backend/.env.example` (outbox lease, max attempts, CLI flags). This runbook is the source of truth for **GitHub** configuration and cutover.

## Secrets vs repository variables

| Kind | GitHub UI | In workflow | Use |
|------|-----------|-------------|-----|
| **Secrets** | Settings → Secrets and variables → Actions → **Secrets** | `secrets.NAME` | Credentials and key material. Encrypted; not shown in logs. |
| **Variables** | Settings → Secrets and variables → Actions → **Variables** | `vars.NAME` | Non-secret production config (hosts, feature flags, tunables). Visible to users with appropriate repo access. |

The worker job receives both. They must match production Render web settings where the names overlap (e.g. `EMAIL_BACKEND`, `FRONTEND_BASE_URL`), except database URLs (see below).

## GitHub Actions secrets (exact names)

Required by `process-email-outbox.yml` (job `env`):

| Secret name | Purpose |
|-------------|---------|
| `SECRET_KEY` | Django `SECRET_KEY` (same as production API). |
| `DATABASE_URL` | **Direct** Neon PostgreSQL URL, role **`ongsho_app`** (not pooler, not owner). |
| `BREVO_API_KEY` | Brevo transactional API key. |
| `INVITE_DELIVERY_ENCRYPTION_KEYS` | JSON map of Fernet keys for plan-invite delivery ciphertext (same as Render). |

Never commit values. Store only in GitHub Secrets and Render.

## GitHub Actions variables (exact names)

Required by `process-email-outbox.yml`. Set in repository **Variables** (not Secrets).

| Variable name | Expected production values (non-secret) |
|---------------|----------------------------------------|
| `OUTBOX_WORKER_ENABLED` | **Workflow gate only** (job `if` in YAML; **not** in job `env` and **not** visible to Django). Must be literal string **`true`** for **any** job run (manual or scheduled). |
| `OUTBOX_SCHEDULE_ENABLED` | **Workflow gate only** (job `if` for `schedule` events; **not** in job `env` and **not** visible to Django). Leave unset / not **`true`** until after a successful confirmed manual run; scheduled cron requires this **and** `OUTBOX_WORKER_ENABLED` == **`true`**. |
| `DEBUG` | `false` |
| `ALLOWED_HOSTS` | Comma-separated hosts (same as Render API). |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated origins (same as Render). |
| `FRONTEND_BASE_URL` | Public webapp base URL (HTTPS, no trailing slash). |
| `FRONTEND_ORIGINS` | CORS origins (comma-separated). |
| `DEFAULT_FROM_EMAIL` | Brevo sender, e.g. `Ongsho <noreply@…>`. |
| `EMAIL_BACKEND` | `core.email_backends.brevo.BrevoEmailBackend` |
| `REFRESH_COOKIE_SECURE` | `true` |
| `REFRESH_COOKIE_SAMESITE` | `None` or `Lax` (match Render). |
| `INVITE_DELIVERY_ENCRYPTION_ACTIVE_VERSION` | Active key version in the JSON map (e.g. `1`). |
| `SECURE_SSL_REDIRECT` | `true` |
| `TRUST_PROXY_SSL` | `true` (if behind Render proxy). |
| `OUTBOX_LEASE_SECONDS` | `900` (default; stale **`processing`** lease expiry before reclaim—not retry backoff). |
| `OUTBOUND_EMAIL_MAX_ATTEMPTS` | `8` (default; cap on failed delivery attempts per row). |
| `BREVO_API_TIMEOUT` | `10` (seconds; optional tuning). |
| `LOG_LEVEL` | e.g. `INFO` |

If a required Django setting is missing, `manage.py process_email_outbox` fails at import time with `RuntimeError` (e.g. missing `DEFAULT_FROM_EMAIL`, missing `INVITE_DELIVERY_ENCRYPTION_KEYS` when `DEBUG=false`).

## Database URLs and roles

| Surface | Env var | Connection | Role | Used for |
|---------|---------|------------|------|----------|
| Render Gunicorn (web) | `DATABASE_URL_POOLED` | Pooled (PgBouncer / `-pooler` host) | `ongsho_app` | HTTP API requests |
| Render / GHA worker & cron commands | `DATABASE_URL` | **Direct** (non-pooler host) | `ongsho_app` | `process_email_outbox`, `run_daily`, shell, etc. |
| Render / CI migrate only | `MIGRATE_DATABASE_URL` | Direct | `neondb_owner` | **`manage.py migrate` only** (not used by this workflow) |

The GitHub worker sets **`DATABASE_URL` only**. It does **not** set `DATABASE_URL_POOLED` or `MIGRATE_DATABASE_URL`. Django selects direct `DATABASE_URL` because `process_email_outbox` is a management command (`backend/config/settings.py`).

Use direct URLs for workers: row claiming uses `SELECT FOR UPDATE SKIP LOCKED` and session advisory locks, which are unsafe through transaction-pooled PgBouncer.

## Schedule and enable conditions

- **Schedule:** cron `*/5 * * * *` (every five minutes, UTC). The workflow event still fires on this cadence; the **job** may be skipped (see gates below).
- **Master gate:** `OUTBOX_WORKER_ENABLED` must equal the exact string **`true`** (case-sensitive; `True` or `1` does **not** enable). If not, **all** job runs are skipped—no checkout, no `manage.py`, no email.
- **Scheduled job** runs only when **both** are **`true`**:
  1. `OUTBOX_WORKER_ENABLED`
  2. `OUTBOX_SCHEDULE_ENABLED`
  3. Event is `schedule`
- **Manual job** runs when **both** hold:
  1. `OUTBOX_WORKER_ENABLED` is **`true`**
  2. Event is `workflow_dispatch` with input `confirm_live_processing` **`true`**
  (Manual runs do **not** require `OUTBOX_SCHEDULE_ENABLED`.)

Unset, empty, or any value other than exact **`true`** for either gate variable is treated as **off**.

**Command run when enabled:**
`python manage.py process_email_outbox --batch-size 50 --max-runtime 55`
(job timeout 10 minutes; concurrency group `ongsho-email-outbox`, `cancel-in-progress: false`).

## Manual execution

1. Actions → **Process email outbox** → **Run workflow**.
2. Set **Confirm live outbox processing** (`confirm_live_processing`) to **`true`**.
3. Ensure `OUTBOX_WORKER_ENABLED` is **`true`** (otherwise the job is skipped).
4. **`OUTBOX_SCHEDULE_ENABLED` may remain off** for a first-run manual pass—scheduled cron will skip until you set it to **`true`** after review.

Manual runs without confirmation never execute the worker, even if `OUTBOX_WORKER_ENABLED` is `true`.

For diagnostics without sending, operators can run locally or in a controlled environment with
`python manage.py process_email_outbox --dry-run` (not used in CI). **Do not** run the full worker against production without authorization.

## Worker behavior (locks, lease, retry, delivery semantics)

Implementation: `backend/core/outbox/` and `backend/core/management/commands/process_email_outbox.py`.

### Advisory lock

- Before processing, the command acquires PostgreSQL advisory lock **`86420102`** (`OUTBOX_WORKER_LOCK_ID`, distinct from `run_daily` lock `86420101`).
- If another worker holds the lock, the command prints `advisory_lock=busy exit=0` and **exits without claiming rows**.
- Lock is released in a `finally` block after the pass (including on errors). Override `--no-advisory-lock` is for tests only—never in production.

### Claiming and lease

- Eligible rows: `pending` / `retry` (due by `next_attempt_at`), plus **`processing`** with `locked_at` older than **`OUTBOX_LEASE_SECONDS`** (stale lease recovery).
- Claims use a short transaction: `SELECT FOR UPDATE SKIP LOCKED`, ordered by `next_attempt_at`, `created_at`.
- Each claimed row gets `status=processing`, `locked_at=now`, unique `locked_by` claim token (UUID hex).

### Send path and retry

- Delivery runs **outside** the claim transaction (Brevo API via `EMAIL_BACKEND`).
- On transient failure: `attempt_count` increments, status → `retry`, `next_attempt_at` from **`BACKOFF_SCHEDULE_SECONDS`** in `core/outbox/retry.py` (fixed step delays in code; optional provider `retry_after` can lengthen the wait). Tunable caps: **`OUTBOUND_EMAIL_MAX_ATTEMPTS`** (env / GitHub var) stops retries; **`OUTBOX_LEASE_SECONDS`** applies only to stale **`processing`** reclaim (see Claiming and lease), not to retry spacing.
- After max attempts: status → `failed`.
- Permanent business errors (e.g. superseded verification, expired invite): status → `cancelled`.
- Success: status → `sent`, optional wipe of `delivery_ciphertext`.

### At-least-once attempts

Delivery is **bounded at-least-once toward Brevo**, not guaranteed single inbox delivery. A crash after Brevo accepts but before the row is marked `sent` can cause a **duplicate provider send** on retry. Plan monitoring around Brevo message logs and outbox row status.

## Safe activation checklist

Complete **before** setting `OUTBOX_WORKER_ENABLED` to **`true`**:

- [ ] Production web deploy includes outbox code; `core` migrations applied via **`MIGRATE_DATABASE_URL`** (owner), not app role.
- [ ] Render: `DATABASE_URL` and `DATABASE_URL_POOLED` use **`ongsho_app`**; encryption keys and Brevo configured; `EMAIL_BACKEND` is Brevo on production.
- [ ] GitHub **Secrets** listed above are set and match production (especially `DATABASE_URL` direct app URL, not pooler).
- [ ] GitHub **Variables** listed above match Render production semantics (`DEBUG=false`, correct `FRONTEND_*`, sender email).
- [ ] Verify outbox queue: no unexpected eligible rows, or explicit acceptance of backlog send volume.
- [ ] Stakeholder sign-off: **authorized to send live email** (not a test environment).
- [ ] **First live pass:** set `OUTBOX_WORKER_ENABLED` to **`true`**; keep `OUTBOX_SCHEDULE_ENABLED` **off**. Run **workflow_dispatch** with `confirm_live_processing=true`; review job logs and Brevo dashboard.
- [ ] **Enable cron only after** that manual pass: set `OUTBOX_SCHEDULE_ENABLED` to **`true`** (with `OUTBOX_WORKER_ENABLED` still **`true`**).

## Rollback (stop scheduled processing)

**Stop scheduled runs only (manual still possible if worker gate is on):**

1. Set **`OUTBOX_SCHEDULE_ENABLED`** to anything other than exact **`true`** (or remove it).
2. Cron workflow events still occur, but scheduled **jobs** skip when the schedule gate is off.

**Stop all GitHub worker runs (scheduled and manual):**

1. Set **`OUTBOX_WORKER_ENABLED`** to anything other than exact **`true`** (or remove it).
2. Confirm scheduled and manual runs show **skipped** job.

**After any rollback:**

3. Cancel any **in progress** run from the Actions UI if needed.
4. Rows left in `processing` with a valid lease are not reclaimed until lease expiry; no new claims while gates are off.
5. To stop **Render** or local cron if configured separately, disable those schedules independently (this runbook covers **GitHub Actions only**).

Rollback does **not** delete outbox rows or undo emails already sent.

## Warnings

- **Enabling the worker can send real email** to real users (verification, invites, reminders, etc.) via Brevo.
- **Do not** set `OUTBOX_WORKER_ENABLED=true` (or enable the schedule gate) or run `process_email_outbox` without authorization on production during informal testing.
- **Do not** point the worker at non-production databases with production Brevo credentials.
- The enable gate is **only** in GitHub Actions; anyone with production DB access and Django env can still run `manage.py process_email_outbox` manually—restrict credentials and operational access accordingly.