# SmartFin — Family Budget Management

A mobile-first PWA for managing a shared household budget. The interface is
Hebrew and right-to-left, and installs to the home screen. Visual language is
**"Gold Fintech"**: a dark hero, floating white cards, a gold accent, and
restrained charts and motion.

🔗 **Live at:** https://smartfin.up.railway.app

## Stack

- **Backend:** Python 3.11 + Flask (Jinja2 templates, served by gunicorn)
- **Database & auth:** Supabase (PostgreSQL + GoTrue), RLS enforced on every table
- **Frontend:** HTML + hand-written CSS + vanilla JS + Chart.js (no build step)
- **Receipt scanning:** OpenAI (`gpt-4o-mini`, vision)
- **Rate limiting:** Flask-Limiter — shared storage via `RATELIMIT_STORAGE_URI`
  (Redis in production), falling back to in-memory counters if it is unreachable
- **PWA:** service worker — stale-while-revalidate for static assets, network-only for API calls
- **Deployment:** Railway (live, region `europe-west4`)

## Project layout

```
SmartFin/
├── backend/
│   ├── app.py                  # all 56 routes: pages, API, auth, hardening
│   ├── clock.py                # Asia/Jerusalem — every "today" in the app comes from here
│   ├── supabase_config.py      # data layer: queries, auth, analytics, recurring engine
│   └── supabase/migrations/    # source of truth for the database schema (48 migrations)
├── frontend/
│   ├── templates/              # base, index, month, months, settings, projects,
│   │                           # project_detail, project_edit, login, onboarding,
│   │                           # reset_password, landing, privacy, terms, error
│   └── static/
│       ├── css/style.css       # the entire stylesheet
│       ├── sw.js, manifest.json, icons/
├── tests/                      # 786 tests: 765 unit (no network) + 21 against the real DB
├── docs/SPEC.md                # product specification
├── Procfile / runtime.txt      # Railway configuration (gunicorn, Python 3.11.9)
└── requirements.txt / requirements-dev.txt
```

## Features

### Main screens

- **Home** — the month's remaining balance (income − expenses − savings), quick
  transaction entry, and recent transactions ordered by insertion. Tapping a
  transaction expands an inline editor in place (amount, category, owner,
  description, date, plus save and delete); project and recurring settings open
  the full modal via "more options".
- **Month** — doughnut charts (where the money went: expenses vs. savings ·
  expenses, income and savings by category · split by family member), anomaly
  alerts, and every transaction of the month. A horizontally scroll-snapped
  strip at the top jumps between every month that has data. Categories expand
  inline to reveal the transactions behind them.
- **Comparison** — the monthly balance over time, with a drill-down into any month.
- **Settings** — profile, categories, projects and account, in an accordion layout.

### Transactions

- Expense / income / savings · edit, delete (with undo) and duplicate from
  anywhere · swipe gestures on mobile · "today / yesterday" quick chips
- Attribution to a family member with a stable per-member color tag (expenses and
  income; savings are always shared)
- **Recurring transactions** — an engine that materializes occurrences
  automatically, both retroactively and forward. Frequencies: monthly on the same
  date, on the 1st and 15th, weekly, and biweekly.
- **Receipt scanning** — photograph a receipt and the amount, merchant, date and
  category are extracted automatically (OpenAI vision). Two ceilings: 100 scans per
  family per month, and `RECEIPT_GLOBAL_MONTHLY_LIMIT` (default 2000) across all
  families, which is what protects the OpenAI bill from an open sign-up form.
  Manual entry is always available.
- Saving a transaction plays a short synthesized two-tone chime and fires haptic
  feedback (`navigator.vibrate`, with a hidden `switch` input as the iOS fallback).

### Projects (a trip, a renovation, an event…)

- Shared with the whole family or private to their owner, convertible in both directions
- Each carries an icon, description, budget target and its own dedicated categories
- A clean overview page (summary, doughnut chart, all transactions) with a
  separate edit screen for every setting
- **Project transactions are excluded from the monthly balance** — a one-off or
  capital expense does not distort the regular month. They are shown separately
  in the "projects this month" section of the month page, and are kept out of the
  home feed and the monthly category drill-downs.

### Analytics

- Anomaly alert: a category exceeding its trailing three-month average
- Per-category monthly budgets, with a progress bar and an overrun warning
- CSV export of any month (`/month.csv`)
- Run-rate forecast: a warning about a projected overrun before the month ends

### Families and accounts

- Invite code plus an onboarding flow for picking a new family's categories
- Sign in by email **or** phone · password reset · password change · profile editing
- A family manager role. Destructive actions — deleting a category, rotating the
  invite code, wiping the family's transactions — are the manager's alone; budgets,
  settings and adding categories stay shared. The rule is enforced in the database,
  not only in the routes.
- Member management: the manager can remove a member, and leaving a family hands
  the role on rather than orphaning it
- Transaction reset and permanent account deletion, backed by an internal
  owner-only archive (nothing is truly lost)
- "Remember me": a 90-day session with automatic token refresh

### Hardening

- `SECRET_KEY` is mandatory — the app refuses to start without it
- Session cookies are `HttpOnly` + `SameSite=Lax`, and `Secure` outside development
- Request bodies capped at 8 MB; uploads restricted to JPG / PNG / WebP
- Rate limits per IP: 10/min on login, 5/min on signup, 3/min on password reset,
  10/min on receipt scanning, and 3/hour on the two irreversible ones — resetting
  transactions and deleting an account
- Amounts, dates and categories are validated on every write path, and a write
  that matched no row reports that instead of "saved"
- `/health` (always 200, for the platform) and `/health/db` (503 when the database
  is unreachable, for an uptime monitor)

## Running locally

```bash
pip install -r requirements.txt
cp .env.example .env          # then fill in the keys
flask --app backend.app run --port 8080
```

> Note: the local server connects to the same Supabase project as production.
> Templates and Python are reloaded only on server restart (no auto-reload by default).

### Environment variables

| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | `https://<ref>.supabase.co` |
| `SUPABASE_KEY` | anon public key |
| `SECRET_KEY` | random string used to sign the session — **required; the app will not start without it** |
| `OPENAI_API_KEY` | OpenAI key — needed only for receipt scanning (without it the button is disabled) |
| `FLASK_ENV` | `development` locally only — **never set in production** (controls cookie hardening and HSTS) |
| `RATELIMIT_STORAGE_URI` | shared rate-limit storage (e.g. a Redis URL). Without it the counters are per-process, which means they barely limit anything across 4 workers — the app logs a warning when this happens in production |
| `RECEIPT_GLOBAL_MONTHLY_LIMIT` | scans per month across **all** families (default 2000) |
| `SENTRY_DSN` | error reporting. Request bodies, cookies and auth headers are stripped before sending |
| `LOG_LEVEL` | `INFO` by default |
| `CSP_REPORT_ONLY` | set while tightening the Content-Security-Policy, so violations are reported instead of blocking |

## Tests

```bash
pip install -r requirements-dev.txt
python3 -m pytest tests/ -m unit -q      # 765 tests, no network, ~7s
python3 -m pytest tests/ -q              # + 21 against the real Supabase project
```

CI runs the unit suite on every push, and Railway is configured to wait for it
before building — so a red test stops the deploy rather than reporting on one
that already shipped. Coverage is measured with a floor (currently ~57%); it is
a floor, not a target, and exists so that coverage cannot disappear quietly the
way it once did over the transaction routes.

The 21 integration tests are marked `rls` and excluded from CI on purpose:
running them needs production keys, and they would also write to the real
database. They use two fixed test accounts — see `tests/setup_rls_test_users.py`,
a one-time script that creates them, with passwords read from the environment and
never from the repo. Caution: more than 10 logins per minute from one IP get a 429.

## Database

The schema lives entirely in `backend/supabase/migrations/`. For a fresh
Supabase project:

```bash
cd backend && supabase link --project-ref <REF> && supabase db push
```

- Every table has RLS enabled. Note that some tables were created with partial
  CRUD coverage — when adding a new write path, check the table's policies first.
- Owner-only internal tables (RLS enabled with **no** policies, so clients
  receive `[]`): `owner_archive`, an archive of everything deleted, and
  `login_events`, a sign-in log.

## Deploying to Railway

The app runs live on Railway (service `smartfin`).

**Critical for performance — region:** the Railway service must run in the same
geographic region as Supabase (here: Railway `europe-west4` against Supabase
`eu-central-1`). Otherwise every query crosses continents (~250 ms instead of
~30 ms) and pages become very slow. Change it under Railway → Service →
Settings → Regions.

**Shipping a new version:** `git push` to `main`. Railway deploys automatically,
and **Settings → Source → "Wait for CI"** is on, so the build waits for GitHub
Actions to go green first. `railway up` still works for a manual push but skips
that gate, so prefer the git path.

**Production environment variables:** `SUPABASE_URL`, `SUPABASE_KEY`,
`SECRET_KEY` (a strong random value, different from the local one),
`RATELIMIT_STORAGE_URI` (without it the limits are per-worker and nearly
meaningless), plus the optional `OPENAI_API_KEY` and `SENTRY_DSN`. Do **not** set `FLASK_ENV` — omitting it enables
secure cookies and HSTS. `PORT` is injected automatically (gunicorn binds to it;
defaults to 8080).

**Supabase Auth:** whenever the domain changes, update `SITE_URL` and
`URI_ALLOW_LIST` to the new domain, or password-reset links will break.

## Before you change anything

Three things in this repo are load-bearing in ways that are not obvious from the
code, and each one has already caused a real incident:

- **Do not add `--threads` to the Procfile, and do not switch to gevent or any
  async worker.** The Supabase client is a process-level singleton whose auth
  header is mutated per request. Sync workers make that safe because each one
  handles a single request at a time. With threads, one user's request runs under
  another user's token — one family reading another's money. The Procfile carries
  the full explanation.
- **Every "today" comes from `backend/clock.py`**, which is `Asia/Jerusalem`. The
  server runs on UTC, so `date.today()` rolls over three hours early and puts
  evening transactions in tomorrow. Tests that patch `datetime.date.today` instead
  of `clock.today()` silently test nothing.
- **`DataUnavailable` is raised, never swallowed.** A query that fails must not
  return zero: a false zero looks exactly like a real one, and the whole app is
  numbers. Returning `[]` or `0` on failure is how a family ends up seeing an
  empty month and believing it.

## Documentation

- `docs/SPEC.md` — the product specification, in Hebrew
- Comments in this codebase explain **why**, not what. Where one is long, it is
  usually because the obvious change there has already been tried and broke
  something.
