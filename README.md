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
- **Rate limiting:** Flask-Limiter (in-memory, auth routes only)
- **PWA:** service worker — stale-while-revalidate for static assets, network-only for API calls
- **Deployment:** Railway (live, region `europe-west4`)

## Project layout

```
SmartFin/
├── backend/
│   ├── app.py                  # all 46 routes: pages, API, auth, hardening
│   ├── supabase_config.py      # data layer: queries, auth, analytics, recurring engine
│   └── supabase/migrations/    # source of truth for the database schema (29 migrations)
├── frontend/
│   ├── templates/              # base, index, month, months, settings, projects,
│   │                           # project_detail, project_edit, login, onboarding,
│   │                           # reset_password, error
│   └── static/
│       ├── css/style.css       # the entire stylesheet
│       ├── sw.js, manifest.json, icons/
├── tests/                      # RLS isolation suite (pytest)
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
  category are extracted automatically (OpenAI vision). Capped at 100 scans per
  family per month; manual entry is always available.
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
- Run-rate forecast: a warning about a projected overrun before the month ends

### Families and accounts

- Invite code plus an onboarding flow for picking a new family's categories
- Sign in by email **or** phone · password reset · password change · profile editing
- Transaction reset and permanent account deletion, backed by an internal
  owner-only archive (nothing is truly lost)
- "Remember me": a 90-day session with automatic token refresh

### Hardening

- `SECRET_KEY` is mandatory — the app refuses to start without it
- Session cookies are `HttpOnly` + `SameSite=Lax`, and `Secure` outside development
- Request bodies capped at 8 MB; uploads restricted to JPG / PNG / WebP
- Auth rate limits per IP: 10/min on login, 5/min on signup, 3/min on password reset

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

## Tests

```bash
pip install -r requirements-dev.txt
python3 -m pytest tests/ -v
```

The RLS isolation suite runs against the real Supabase project using two fixed
test accounts (see `tests/setup_rls_test_users.py`, a one-time script that
creates them). Caution: more than 10 logins per minute from the same IP are
rejected with a 429.

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

**Shipping a new version:** `git push` to `main`, then `railway up` (uploads and rebuilds).

**Production environment variables:** `SUPABASE_URL`, `SUPABASE_KEY`,
`SECRET_KEY` (a strong random value, different from the local one) and
`OPENAI_API_KEY` (optional). Do **not** set `FLASK_ENV` — omitting it enables
secure cookies and HSTS. `PORT` is injected automatically (gunicorn binds to it;
defaults to 8080).

**Supabase Auth:** whenever the domain changes, update `SITE_URL` and
`URI_ALLOW_LIST` to the new domain, or password-reset links will break.
