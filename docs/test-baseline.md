# Backend test baseline

Reproducible record of the Ongsho Django backend pytest suite after **Stage 5.2** remediation (through **5.2e**).

**Last full run:** 2026-11-26 (UTC+6) — Stage 5.3 observability + CI workflows  
**Passing this document does not prove production behaviour.** It only records automated tests against a PostgreSQL test database (`test_ongsho`). Live verification still requires staging/production smoke checks, email provider delivery, and real payment rails.

---

## Environment requirements

| Requirement | Notes |
|-------------|--------|
| Python | Project `backend/requirements.txt` (tested with Python 3.14 in CI-like local runs) |
| PostgreSQL | Required for full suite (advisory locks, concurrency, some billing/job tests) |
| `SECRET_KEY` | Required by `config.settings` |
| `TEST_DATABASE_URL` | **Preferred for pytest:** direct URL to a database Django may use as the test DB (e.g. `postgresql://…/test_ongsho?sslmode=…`). When set during pytest, `_database_config()` uses it with `conn_max_age=0`. |
| Other env | If `TEST_DATABASE_URL` is unset, pytest falls back to normal `DATABASE_URL` / pooled URLs per `config/settings.py` (see `tests/test_settings_database.py`). |

### Standard full-suite command

From the repository root:

```bash
cd backend
python -m pytest
```

Optional verbosity:

```bash
python -m pytest --tb=short -q
```

`pytest.ini` sets `DJANGO_SETTINGS_MODULE=config.settings` and `testpaths=tests`.

### Post-test repository checks (2026-11-25)

```bash
cd backend
python manage.py makemigrations --check --dry-run   # exit 0 — no pending migrations
python manage.py check                               # exit 0 — no issues
```

From repo root:

```bash
python backend/scripts/scan_secrets.py               # exit 0 — no findings (file + rule only)
```

No backend-wide Ruff/Black/pre-commit config was found in this repository at baseline time; backend formatting/lint is not part of the local baseline gate below.

### GitHub Actions CI (`.github/workflows/ci.yml`)

CI is **wired in the repository** (Stage 5.3). This document records **local** run results; a green local run does not imply a green GitHub Actions run unless you have observed one.

| Job | Steps (each step fails the job on non-zero exit) |
|-----|--------------------------------------------------|
| **backend** | Full `python -m pytest` on PostgreSQL 16 service · `makemigrations --check --dry-run` · `manage.py check` · `scripts/scan_secrets.py` |
| **frontend** | `npm ci` · `npm test` (Vitest) · `npm run lint` (ESLint) · `npm run build` · `npm run check:dist` |

Operational detail: `docs/operations-ci-jobs.md`. Optional workflows (`run-daily-job.yml`, `process-email-outbox.yml`) are **not** part of this quality CI and remain gated off by default.

---

## Latest full-suite result

| Metric | Value |
|--------|------:|
| **Passed** | **1881** (Stage 5.6 closeout; was **1879** at 5.3) |
| **Failed** | **0** |
| **Skipped** | **2** |
| **Warnings** | **3** (see below) |
| **Runtime** | **~212 s** (3m 32s wall on 2026-11-26 run) |

**Frontend (Vitest, `frontend/webapp`):** **105 passed**, 28 files, ~17s (2026-11-26).

CI workflow definitions: `.github/workflows/ci.yml` (quality only). Operational guide: `docs/operations-ci-jobs.md`.

Skipped tests (conditional, not failures):

1. `tests/test_billing_schedule_consistency.py` — renewal not defined while subscription **cancelled**
2. Same file — renewal not defined while subscription **paused**

Warnings (non-fatal):

- `tests/test_dev_db_guard.py` — Django `UserWarning` when overriding `DATABASES` in tests (expected).
- `tests/test_transfers_matrix.py::test_accept_races_cancel` — occasional **teardown** `OperationalError` if other sessions hold `test_ongsho` (environment/concurrency; run did not fail tests).

---

## Stage 5.1 → 5.2 remediation map

**Original triage (Stage 5.1/5.2):** **1851 passed**, **13 failed**, **2 skipped**.

All 13 failures were addressed in Stage 5.2 sub-stages; none remain in the latest full run.

| Area | Stage | Original failures | Resolution |
|------|-------|-------------------|------------|
| Owner mark-paid / `tid_required` | **5.2a** | 6 payment API tests | Removed erroneous `tid_required` block for owners in `payments/services.py` (`mark_due_paid`). Members still cannot mark paid (404). Owner cash mark-paid **without** transaction ID remains supported. |
| Billing list / active cycle | **5.2b** | 3× `test_billing_from_back_charges.py` | Tests aligned with **approved policy**: charges allowed when billing period is **active** *or* due date is within **10-day lead** (`CHARGE_LEAD_DAYS`). Implementation in `billing/services.py` unchanged. |
| Secret scanner fixtures | **5.2c** | `test_secret_scan_script_clean` | Per-match test-fixture exemptions in `scripts/scan_secrets.py` (Brevo/JWT/Postgres-shaped **demonstrable** fixtures only under `backend/tests/`). Production rules unchanged. |
| Query budgets | **5.2d** | 3 performance tests | Fixed N+1/count regressions: `is_owner_seat` subscription `COUNT` storm, redundant Due fetches, batched tab counts; **read-only** owner list enrichment (`read_only=True`) on `GET /api/subscriptions/`. |

### Approved policies (do not regress without explicit product decision)

1. **Mark-paid:** Plan owners may mark dues paid in cash **without** a transaction ID; members cannot use owner mark-paid endpoints.
2. **Billing generation:** Keep `in_active_cycle` in `generate_missing_charges`. Charge when the period is active **even if** due date is &gt; 10 days away, **or** when due date is inside the 10-day lead window.
3. **Secret scanning:** No blanket `backend/tests/` ignore. Rule-specific safe fixture patterns only; realistic secrets in tests must still fail unless they match those patterns.
4. **Query budgets / list GET:** Owner subscription list enrichment is **read-only** (no charge/dues side effects on list); use prefetched context, `owner_id` for `is_owner_seat`, and batched counts. Budgets in `tests/test_performance_budgets.py` and `tests/test_member_due_enrichment.py` remain meaningful.

---

## Areas explicitly covered in full suite

Non-exhaustive but includes Stage 5.2-sensitive modules:

- Payment decisions, pending rejection, owner/member permissions
- Billing generator, `billing_from`, schedule consistency
- `tests/test_static_security.py` (including secret scanner subprocess + unit fixtures)
- Performance budgets and member due enrichment query counts
- Email outbox: verification, password, email change, payment rejection, account closure (`tests/test_*_outbox*.py`, worker, dispatch)
- Account closure notification cancellation
- Transfers, reminders, calendar, subscriptions API

---

## Known limitations

| Item | Status |
|------|--------|
| CI vs local | Quality CI is defined in `.github/workflows/ci.yml` (see table above). Local runs may diverge (Python/Node versions, DB teardown, ESLint cache). |
| Skipped tests | 2 conditional skips in billing schedule consistency (paused/cancelled). |
| Teardown warning | `test_ongsho` in use by other sessions — close idle DB clients if teardown errors appear. |
| Production | Email delivery, Brevo, Neon pooler behaviour, and payment providers require live/staging checks beyond pytest. |

---

## Historical comparison

| Date | Passed | Failed | Skipped | Notes |
|------|-------:|-------:|--------:|-------|
| Stage 5.1/5.2 triage | 1851 | 13 | 2 | Pre-remediation baseline |
| **2026-11-25 (5.2e)** | **1869** | **0** | **2** | After 5.2a–5.2d |
| **2026-11-26 (5.3)** | **1879** | **0** | **2** | CI + outbox/run_daily observability tests |
| **2026-11-26 (5.6 closeout)** | **1881** | **0** | **2** | +2 subscription list pagination/totals tests; frontend ESLint gate clean locally |

**Stage 5.3 reference (local):** backend **1879** passed, **2** skipped; frontend Vitest **105** passed (`frontend/webapp`).

The pass count increase vs 1851 is expected: former failures now pass, plus minor growth in the test module count over the stage series.