# Outbound email worker — operations runbook

## Worker command (production cron)

From the `backend/` directory:

```bash
python manage.py process_email_outbox --batch-size 50 --max-runtime 55
```

- **`--batch-size`**: maximum rows claimed per batch (default `50`).
- **`--max-runtime`**: stop after N seconds (default `0` = run until the queue is empty or a partial batch). Use a value below the cron interval for scheduled jobs (e.g. `55` for a 1-minute schedule).
- **`--worker-id`**: label for stdout only; **not** stored in `locked_by`. Each claimed row gets its own per-claim UUID token in `locked_by`.
- **`--dry-run`**: prints `eligible=<count>` without claiming or sending.
- **`--no-advisory-lock`**: skip the PostgreSQL advisory lock (diagnostics/tests only).

On normal completion the command prints:

`worker_id=… claimed=… sent=… retry=… failed=… cancelled=… skipped_ownership=…`

If another worker session already holds the lock:

`advisory_lock=busy exit=0`

Exit code `0` in both cases — a busy lock means **this run did not process mail**, not that the queue is empty.

## Database requirements

| Service | URL variable | Notes |
|---------|--------------|--------|
| **Web (Gunicorn)** | `DATABASE_URL_POOLED` | PgBouncer transaction pooling; `DB_CONN_MAX_AGE` default 60. |
| **Worker / migrate / run_daily** | `DATABASE_URL` | Direct Neon PostgreSQL session. |

### Why the worker must use direct `DATABASE_URL`

The command uses **session-level** PostgreSQL advisory locks (`pg_try_advisory_lock` / `pg_advisory_unlock`, lock id `86420102`). Those locks are tied to the database **session**. PgBouncer transaction pooling can hand each statement to a different server session, which breaks lock acquire/release pairing and can allow overlapping cron runs.

### How Django selects the URL

In `config.settings`, `_use_direct_database_url()` is true when `sys.argv` contains a management command name such as `process_email_outbox`, `migrate`, or `run_daily`. The web process (Gunicorn) does not use that path, so it keeps `DATABASE_URL_POOLED`.

Example URLs in `.env.example` use `?sslmode=require` for Neon.

## Required environment variable names (no values)

Worker and web share the same Django settings module. For production mail delivery the worker needs at least:

- `SECRET_KEY`
- `DATABASE_URL` (worker cron) / `DATABASE_URL_POOLED` (web)
- `DEFAULT_FROM_EMAIL`
- `FRONTEND_BASE_URL`
- `EMAIL_BACKEND` (e.g. `core.email_backends.brevo.BrevoEmailBackend`)
- `BREVO_API_KEY`
- `INVITE_DELIVERY_ENCRYPTION_KEYS`
- `INVITE_DELIVERY_ENCRYPTION_ACTIVE_VERSION`

Operational tuning (defaults in settings):

- `OUTBOX_LEASE_SECONDS` (default `900`) — reclaim stale `PROCESSING` rows.
- `OUTBOUND_EMAIL_MAX_ATTEMPTS` (default `8`) — cap retry attempts before `FAILED`.
- `BREVO_API_TIMEOUT` (optional)

## Row status meanings

| Status | Meaning |
|--------|---------|
| **PENDING** | Queued; eligible when `next_attempt_at` is null or due. |
| **PROCESSING** | Claimed by a worker; `locked_at` / `locked_by` (claim token) set. |
| **RETRY** | Last attempt failed retryably; wait until `next_attempt_at`. |
| **SENT** | Provider send succeeded; invite ciphertext cleared when applicable. |
| **CANCELLED** | Business rule made delivery unnecessary (e.g. opt-out, stale invite). |
| **FAILED** | Permanent failure or **max attempts** exhausted (`last_error_code`, e.g. `max_attempts`). |

### Retry backoff

On retryable errors, `attempt_count` increments and `next_attempt_at` is set using the built-in backoff schedule (60s → 5m → 15m → … up to 12h steps). HTTP 429 may honour a longer provider delay when present.

### Maximum attempts

When `attempt_count` reaches `OUTBOUND_EMAIL_MAX_ATTEMPTS` after a failed attempt, status becomes **FAILED** with `last_error_code=max_attempts`. Rows are **not** automatically re-enqueued.

### Stale `PROCESSING` recovery

If `locked_at` is older than `OUTBOX_LEASE_SECONDS`, the row becomes eligible again and may be reclaimed with a **new** claim token. An old worker finishing late gets `skipped_ownership` and cannot mutate the row.

### Advisory lock vs queue drain

`advisory_lock=busy exit=0` only means this cron invocation did not acquire lock id `86420102`. Another session may be running, or a stale session may still hold the lock until disconnect.

## Troubleshooting (safe checks)

1. **Dry-run queue depth:** `python manage.py process_email_outbox --dry-run` → `eligible=N`.
2. **Missing Brevo key:** rows may fail with `config_missing` / permanent `FAILED`; logs show `brevo_email_skipped reason=missing_api_key` when the backend cannot send.
3. **Missing encryption keys:** Django refuses to start in production (`DEBUG=False`) without `INVITE_DELIVERY_ENCRYPTION_KEYS`; plan-invite rows may fail with `decrypt_failed` if keys do not match ciphertext version.
4. **Growing PENDING/RETRY:** confirm cron is scheduled, uses **direct** `DATABASE_URL`, and is not always printing `advisory_lock=busy`.
5. **Stale PROCESSING:** check `locked_at` vs `OUTBOX_LEASE_SECONDS`; wait for lease expiry or investigate crashed workers.
6. **FAILED rows:** inspect `last_error_code` in Django admin (read-only **OutboundEmail**) or SQL; do not bulk-update status without a defined runbook change.
7. **Worker not running:** eligible count rises; no `claimed=` lines in cron logs.
8. **Repeated advisory busy:** overlapping schedules, long-running worker (`--max-runtime` too high), or a stuck DB session holding the lock.

## Django admin

Staff users can list and view **OutboundEmail** read-only (no add/delete/edit). Sensitive fields excluded: `to_email`, `payload`, `delivery_ciphertext`. Operational fields include type, status, attempts, error codes, FK ids, and timestamps.

## Render (manual configuration)

The repository does not define a `render.yaml`. Operators must configure in the Render dashboard:

- Cron (or worker) service start command with `process_email_outbox` as above.
- Environment: same secrets as web **plus** ensure cron uses `DATABASE_URL` (direct); web keeps `DATABASE_URL_POOLED`.
- Do not run the outbox worker against production from local shells as part of normal ops.