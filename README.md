<!-- markdownlint-disable MD033 MD041 -->

<div align="center">

<img src="docs/assets/readme-hero.svg?v=3" alt="Ongsho — split subscriptions, track every due, keep the record" width="100%" style="max-width:1200px;border:4px solid #000;border-radius:24px;box-shadow:8px 8px 0 #000;" />

<br />

<img src="docs/assets/ongsho-mark.svg?v=3" alt="" width="88" height="88" />

# Ongsho

### The group chat is **not** a ledger.

**Ongsho** is a cooperative subscription and accounting web app for people who split streaming, tools, and shared services.  
One clear **Due · Pending · Paid · Waived** status per seat — not screenshots in a chat thread.

<br />

[![React](https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react&logoColor=000)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-8-646CFF?style=for-the-badge&logo=vite&logoColor=fff)](https://vitejs.dev/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-4-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=fff)](https://tailwindcss.com/)
[![Django](https://img.shields.io/badge/Django-5+-092E20?style=for-the-badge&logo=django&logoColor=fff)](https://www.djangoproject.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=for-the-badge&logo=postgresql&logoColor=fff)](https://www.postgresql.org/)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=fff)](https://www.python.org/)

</div>

---

## What Ongsho is

Ongsho helps **plan owners** (including **Reseller**-mode plans that only collect) and **members** on shared plans manage subscriptions together: invite people by email, track who owes what, review payment proofs, and keep a dependable monthly record.

**Who it’s for**

- Friend groups splitting Netflix, Spotify, ChatGPT, and similar services  
- Owners collecting via bKash, Nagad, Rocket, bank transfer, or cash  
- Anyone tired of “I’ll send it tomorrow” with no paper trail  

**What it is not**

- Ongsho does **not** move money or connect to payment gateways. **Payments happen outside Ongsho; Ongsho only keeps the record.**  
- Ongsho does **not** offer integrated printing — you download PDFs and print from your own device if you need paper.  
- Ongsho does **not** ship spreadsheet/CSV export for general data dumps (verified in the codebase).

The product UI is tuned for a **vibrant, neo-brutalist** identity: cream surfaces (`#fdfbcf`), brand red (`#bf1d1d`), hard black borders, and bold display type — the same language as the public landing page.

---

## At a glance

| | |
|---|---|
| **Type** | Full-stack SaaS web application |
| **Frontend** | React 19 + Vite 8 + Tailwind CSS 4 + TanStack Query |
| **Backend** | Django 5 + Django REST Framework + JWT authentication |
| **Database** | PostgreSQL (designed for managed hosting such as Neon) |
| **PDFs** | ReportLab — dynamically generated monthly statements |
| **Email** | Transactional messages (e.g. verification, receipts, reminders) via a configured email provider |
| **Typical deployment** | React on **Vercel**, API on **Render**, database on **Neon** |
| **Timezone** | Asia/Dhaka (Bangladesh) for business dates and reminders |

The React app talks to the API through **same-origin `/api` paths** in production (Vercel rewrites to the backend). Locally, Vite proxies `/api` to the Django dev server.

---

## Feature showcase

Features below were verified against the **React routes**, **API modules**, and **Django apps** in this repository. Mock/demo mode exists for offline exploration (`VITE_FORCE_MOCK=true`); production-style behavior uses the live API list in `frontend/webapp/src/api/modes.js`.

### Dashboard and overview

| Capability | Who | Where |
|------------|-----|--------|
| Home dashboard with monthly spend, owned vs joined split, “due soon”, rarely used plans | Signed-in user | `/app` |
| Six-month spend forecast and category breakdown | Signed-in user | `/app` |
| “Needs attention” items and next-seven-days snapshot | Signed-in user | `/app` |
| Owner vs member plan summaries on one screen | Signed-in user | `/app` |

**Why it matters:** Owners see collection load and review queues; members see what they owe across every shared plan.

### Plans, seats, and membership

| Capability | Who | Where |
|------------|-----|--------|
| Create and edit **Owner** or **Reseller** plans with seats, pricing, trials, renewal rules | Plan owner | `/app/plans`, `/app/plans/new`, `/app/plans/:id/edit` |
| Preset **categories** and **service names** (streaming, AI tools, etc.) plus custom entries | Plan owner | Plan form & catalog APIs |
| **Email invites** and **join links** for new or existing users | Plan owner | Plan detail, `/invite/:token`, `/join/:token` |
| Replace members, manage leave requests, **ownership transfer** | Plan owner / invitee | Plan detail, notifications actions |
| View plans you **own** vs plans you **joined** | User | `/app/plans`, `/app/shared` |
| Request or cancel **leave** from a shared plan | Member | Shared plan detail |
| Pause, resume, cancel, or archive plans | Owner | Owner plan UI |

### Dues, payments, and review

Each seat moves through **Due → Pending → Paid** (or **Waived**) with optional notes and transaction IDs (bKash, Nagad, Rocket, mobile banking, bank, cash, other).

| Capability | Who | Where |
|------------|-----|--------|
| Submit a payment with method, amount, transaction ID, note | **Member** on the plan (not the subscription owner) | Shared plan / pay modals |
| **Confirm**, **reject**, or **reverse** submitted payments | Plan owner | Notifications, `/app/plans/:id/review`, owner plan rows |
| **Mark due as paid** or **waive** charges | Plan owner | Owner plan & review flows |
| Payment **ledger** / activity on owner plan | Owner | `/app/plans/:id` |
| Review queue for pending payments | Owner | `/app/plans/:id/review` |

**Workflow:** Members **submit proof**; owners **review and confirm**. Confirmation updates dues and can trigger a **payment receipt email** to the payer (email, not a PDF attachment in the verified flows).

### Calendar

| Capability | Who | Where |
|------------|-----|--------|
| Month view of renewals, dues, and related events | Signed-in user | `/app/calendar` |

### In-app notifications

| Capability | Who | Where |
|------------|-----|--------|
| Filterable inbox (all, needs action, payments, plans, reminders) | Signed-in user | `/app/notifications` |
| Mark read / mark all read | Signed-in user | Notifications page |
| **Actionable** items: approve/reject payments, accept/decline invites & transfers, open leave requests | Owner / member | Notification rows |
| Parallel **transactional email** for the same events (verification, password security, invites, reminders, payment confirmed/rejected, etc.) | Account holders | Inbox + email |

Verified notification kinds include payment lifecycle, plan invites, leave/transfer, renewal/trial/expiry reminders, and account email change — see `backend/notifications/kinds.py`.

### Account, profile, and security

| Capability | Who | Where |
|------------|-----|--------|
| Register, login, logout | Guest / user | `/register`, `/login` |
| **Email verification** and resend | New user | `/verify-email` |
| **Password reset** request and confirm | User | `/reset-password` |
| Profile, password change, **email change** with verification | User | `/app/profile` |
| **Reminder preferences** (renewal / due emails) | User | Profile / reminder settings |
| **Close account** with safeguards | User | Profile |

### Reminders

Automated **renewal**, **trial end**, **expiry**, and **due soon** reminders (in-app + email when configured), respecting user reminder settings.

---

## PDF documents and downloadable statements

Ongsho **generates real PDF files in memory** (ReportLab) and returns them as downloads — not pre-stored files on disk for each request.

| Document | Contents (product level) | Who can download | Where in the app |
|----------|--------------------------|------------------|------------------|
| **Owner monthly statement** | Plan-level summary for a selected month (amounts in BDT formatting, branding) | Subscription **owner** | Owner plan detail — **Download statement** |
| **Member monthly statement** | Member’s share for a selected month on a joined plan | **Member** on that plan (not the subscription owner on the same plan) | Shared plan detail — **Download statement** |
| **Roster member statement** | Same member-scoped PDF, generated for a specific member row | **Owner** viewing that member | Owner plan member panel — **Download statement** |

**Verified behavior**

1. Response `Content-Type: application/pdf` with a downloadable filename.  
2. Statement **number** returned for display (`X-Statement-Number` header).  
3. Owner/member downloads may create or reuse a **Statement** audit row; owner roster download generates the PDF **without** requiring a separate stored file.  
4. Users may **print** a downloaded PDF with their own PDF reader — that is not an Ongsho printing service.

**Not offered (verified absent):** payment receipt PDFs (receipts are **email**), CSV/Excel exports, or arbitrary “export all data” downloads.

---

## Technology stack

### Frontend (`frontend/webapp`)

- **React 19** with **React Router 8**  
- **Vite 8** build tool  
- **Tailwind CSS 4** (`@tailwindcss/vite`) — neo-brutalist theme in `src/styles/theme.css`  
- **TanStack Query** for server state  
- **Axios** HTTP client with live/mock delegation  
- **Lucide React** icons · **Recharts** charts  
- **Vitest** + Testing Library · **ESLint 10**

### Backend (`backend`)

- **Python 3.12+** (CI uses 3.12)  
- **Django 5+**, **Django REST Framework**, **SimpleJWT**  
- Apps include **accounts**, **plans**, **billing**, **sharing**, **dues**, **payments**, **notifications**, **reports**, **catalog**, **audit**, **jobs**, **core**  
- **Gunicorn** + **WhiteNoise** for production static assets  
- **ReportLab** for PDF statements  
- **pytest** + **pytest-django** (large automated suite in CI)

### Data & ops

- **PostgreSQL**  
- **GitHub Actions** CI (backend PostgreSQL service + frontend lint/test/build)  
- **Brevo** (or console backend locally) for outbound mail — configured via environment, not hard-coded in the repo

---

## Architecture

1. The user loads the **React SPA** from frontend hosting.  
2. Browser calls **same-origin `/api/...`**; hosting rewrites those requests to the **Django API**.  
3. Django reads/writes **PostgreSQL** and enqueues **transactional email** when needed.  
4. **JWT access tokens** (short-lived) and **HTTP-only refresh cookies** secure sessions — details intentionally omitted here.

---

## Project structure

```text
Ongsho/
├── backend/                 # Django project (config/, domain apps, tests, manage.py)
│   ├── accounts/            # Auth, profile, me endpoints
│   ├── plans/               # Subscriptions & plan lifecycle
│   ├── sharing/             # Shared plans, members, invites, transfers
│   ├── billing/             # Charges & billing periods
│   ├── dues/                # Per-member dues
│   ├── payments/            # Submit / confirm / reject payments
│   ├── notifications/       # In-app notifications & reminders
│   ├── reports/             # PDF statements
│   └── tests/               # Pytest suite
├── frontend/webapp/         # React SPA (src/features, src/api, src/styles)
├── docs/assets/             # README artwork (SVG)
└── .github/workflows/       # CI pipelines
```

---

## Getting started (local development)

You need **Python 3.12+**, **Node.js** (for the frontend toolchain), and a **PostgreSQL** database.

### 1. Clone

```bash
git clone https://github.com/yasin-coded/Ongsho.git
cd Ongsho
```

### 2. Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
```

Copy environment templates and fill in **local-only** values (never commit real secrets):

- Repository root `.env` and/or `backend/.env` — see `backend/.env.example` for required variable **names** (e.g. `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DATABASE_URL`, `FRONTEND_BASE_URL`, …).

Run migrations and start the API:

```bash
python manage.py migrate
python manage.py runserver
```

Default dev URL: `http://localhost:8000`

### 3. Frontend

```bash
cd frontend/webapp
npm install
```

Copy `frontend/webapp/.env.example` to `.env.local` if needed (`VITE_API_URL=` empty uses the Vite proxy).

```bash
npm run dev
```

Open the URL Vite prints (typically `http://localhost:5173`). API requests to `/api` proxy to port **8000**.

### Optional mock mode

Set `VITE_FORCE_MOCK=true` to run the UI against the in-memory mock database with no backend — useful for UI demos, not for validating production API behavior.

---

## Testing and code quality

### Backend (from `backend/`)

```bash
python manage.py check
python -m pytest
python manage.py makemigrations --check --dry-run
```

CI also runs a repository secret scan script. Test counts change over time; CI is the source of truth for merge health.

### Frontend (from `frontend/webapp/`)

```bash
npm run lint
npm test
npm run build
```

Automated tests cover API adapters, auth flows, and critical UI logic so refactors to plans, payments, and statements stay safe.

---

## Security and privacy (public)

- **Authentication required** for app APIs; role-aware rules separate owners, members, and outsiders.  
- **Email verification** and secure password flows for account recovery.  
- **HTTPS** and security headers in production configurations.  
- Sensitive values live only in **environment configuration**, not in source control.

If you discover a security issue, please use **[GitHub Private Vulnerability Reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)** for this repository (or contact the maintainer through an agreed channel). Do not open public issues with exploit details.

---

## Deployment overview (informational)

| Layer | Typical hosting |
|-------|-----------------|
| React SPA | Vercel (static build + `/api` rewrites) |
| Django API | Render (Gunicorn) |
| PostgreSQL | Neon |
| Email | Provider configured in backend environment |

Production deployment requires a full environment setup (secrets, database URLs, CORS origins, email provider, static file collection on the API service, etc.). This README is **not** a production runbook.

**Render build note (operators):** append `python manage.py collectstatic --noinput` after dependencies are installed so operator-facing Django static assets are served correctly.

---

## Contributing

1. **Fork** the repository and create a feature branch from `main`.  
2. Make focused changes; match existing code style (backend services/selectors/views split; frontend feature folders).  
3. Run **backend pytest** and **frontend lint/test** for anything you touch.  
4. Open a **pull request** with a clear description and test notes.

No separate `CONTRIBUTING.md` policy file exists yet; use common sense and keep diffs reviewable.

---

## License

No `LICENSE` file is present in this repository at the time of writing. **Licensing has not been specified publicly** — do not assume open-source terms until a license is added.

---

## Closing

**Manage all subscriptions in one place.**  
Ongsho turns informal splitting into a shared record everyone can trust — colourful UI, serious dues, and PDF statements when you need proof on paper.

Built by **Yasin Bin Ahsan**. Product identity and copy align with the live landing experience in `frontend/webapp/src/features/landing/`.

---

<p align="center">
  <img src="docs/assets/ongsho-mark.svg?v=3" alt="" width="56" height="56" />
  <br />
  <strong>Ongsho</strong> — split fairly. Track clearly. Download when it counts.
</p>