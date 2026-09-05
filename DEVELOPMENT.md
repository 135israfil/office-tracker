# Development Setup

Requirements as specified in `README.txt` §32; the build plan lives in
`claudedocs/PLAN.md`. This file only covers getting the stack running.

## Prerequisites

- Docker (for PostgreSQL; optionally the whole backend)
- Python 3.10 for the backend — not a preference: the production target runs
  PostgreSQL 10.23, Django 4.0 is the last release series that supports it, and 3.10 is
  the newest Python Django 4.0 supports. See `backend/requirements.txt`. (The desktop
  agent is a separate Python project with no such constraint — see its own README.)
- Node.js 22

## Quick start

```bash
cp .env.example .env          # adjust if your ports clash

docker compose up -d db       # PostgreSQL on :5432

cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt   # Windows
# source .venv/bin/activate && pip install -r requirements-dev.txt   # macOS/Linux

.venv/Scripts/python manage.py migrate
.venv/Scripts/python manage.py createsuperuser
.venv/Scripts/python manage.py runserver
```

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

The home page calls `/api/health/` and shows the backend status, which is the quickest
way to confirm the two halves are talking to each other.

Copy `.env.example` to `.env` before the first run. One value in it matters more than it
looks: `DJANGO_CSRF_TRUSTED_ORIGINS` must name the dev server's origin
(`http://localhost:5173`). In development the frontend and the API are different origins,
and Django checks the `Origin` header on every unsafe request against that list — so
without it, signing in appears to work while every save, enrolment and check-in fails
with a 403. Signing in is the one exception because DRF only enforces CSRF once a session
exists, which makes the symptom look like a permissions bug rather than a config gap.

## Running everything in Docker

```bash
docker compose up --build
```

Backend on `:8000`, database on `:5432`. The backend container runs migrations on start
and mounts `./backend`, so code edits reload without a rebuild. The frontend is not
containerised — Vite's dev server is better run on the host.

## Running the desktop agent

```bash
cd desktop-agent
pip install -r requirements-dev.txt          # or use the backend venv

# Enrol against a running backend. Create the computer in the web app first
# (Computers -> Enrol computer) to get the code.
python -m agent --server http://localhost:8000 --enroll ABCDE-FGHJK
python -m agent --headless                   # heartbeat loop without a tray icon
python -m agent --status
```

Set `OFFICE_AGENT_DATA_DIR` to a scratch directory while developing so the agent never
touches a real installation's `%PROGRAMDATA%\OfficeTracker` config.

Marking silent machines offline is a scheduled job, the same shape as the absentee job:

```bash
cd backend
python manage.py mark_offline_computers --dry-run
python manage.py mark_offline_computers      # run every minute from cron
```

## Checks

Run these before pushing; CI runs exactly the same set.

```bash
# backend
cd backend
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m black --check .
.venv/Scripts/python -m pytest --cov
.venv/Scripts/python manage.py makemigrations --check --dry-run

# repo-wide privacy guard (README §31)
python scripts/check_privacy.py

# desktop agent
cd desktop-agent
python -m ruff check .
python -m black --check .
python -m pytest -q

# frontend
cd frontend
npx eslint src --ext .js,.vue --max-warnings 0
npm run build
```

Optionally install the git hooks so most of this runs automatically:

```bash
pre-commit install
```

## Things worth knowing

- **`AUTH_USER_MODEL` is `accounts.User`** and was set before the first migration.
  Do not attempt to swap it later.
- **All timestamps are stored UTC.** `settings.TIME_ZONE` is UTC and stays that way; the
  office-local timezone that decides which calendar date an attendance record belongs to
  is application data (`AppSettings`), not a Django setting. See PLAN.md A1.
- **Settings read from the environment only.** Nothing environment-specific is hardcoded,
  so the same image runs in dev, CI and production. `SECRET_KEY` has an insecure fallback
  *only* when `DJANGO_DEBUG=true`; with debug off, a missing key is a hard failure.
- **The device token is never on disk.** The agent stores it in Windows Credential
  Manager through `keyring`, with no plaintext fallback, and the server keeps only a
  SHA-256 hash. A lost token means a new enrollment code, not a lookup.
- **Nothing is marked synced before the server confirms it.** The agent writes every
  closed session to its local SQLite queue first and clears the flag only on a 2xx, so
  the failure mode it accepts is "uploaded twice" — harmless, because ingestion upserts
  on `client_event_id` — and the one it rules out is "uploaded but lost".
- **A PC being off is inferred, never awaited.** Crashes and power cuts send no shutdown
  event, so three missed heartbeats close the open session at the *last heartbeat* time.
  Anything the agent reports on the way out only sharpens that timestamp.
- **The privacy guard is not advisory.** `scripts/check_privacy.py` fails the build on any
  import capable of screen capture, key logging, camera, microphone or clipboard access.
  If it ever blocks legitimate work, change it deliberately and say why.
- **`uiautomation` is permitted for reading only.** The browser collector cannot read an
  address bar without it, but the same library can synthesise input and grab bitmaps. The
  guard rejects those calls by name (`SendKeys`, `Click`, `CaptureToImage`, …), so a
  method of your own with one of those names will trip it. Rename yours.
- **Activity totals are clipped to the day, and never summed across types.** A session
  spanning midnight belongs partly to each date, and ACTIVE / APPLICATION / WEBSITE
  sessions deliberately overlap — `activities/queries.py` is the only place that decides
  either rule.
- **Clock times are displayed in the office timezone**, which travels with every
  dashboard payload. The viewer's locale decides formatting, never which hour it was.
  Exports render the timestamp in office-local terms server-side for the same reason —
  a CSV has no timezone to travel with it.
- **An export is the whole filtered range, never the page on screen.** The JSON report
  endpoints page; `/api/reports/{type}/export/` does not. CSV is streamed row by row and
  is the format to use for a long range; the xlsx is assembled whole because a zip's
  directory is written last. Excel cells carry real durations (`[h]:mm`) so a column of
  PC time sums, which is the first thing anyone does to a timesheet.
- **Report exports are written to the audit log**, on stream completion rather than on
  request, with the filters and the row count. Ordinary reads are not audited; an export
  is, because the data leaves in a file that then travels on its own.
- **Only the domain is ever stored for websites.** Truncation happens inside the
  collector, before anything reaches disk or the network, and the server re-validates the
  field as a bare host. Two layers, because the failure this prevents is a privacy
  incident rather than a bug.
