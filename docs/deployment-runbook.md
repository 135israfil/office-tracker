# Deployment runbook

How to put this system into production and keep it running. `DEVELOPMENT.md` covers
running it on a laptop; this covers running it for an office.

Everything here has been exercised except the two steps that need infrastructure this
repository cannot provide — a real TLS certificate and a real Windows fleet. Those are
marked **[unverified]** where they appear, with what to check instead.

---

## 1. What you are deploying

| Piece | What it is | Where it runs |
|---|---|---|
| Backend | Django + DRF, gunicorn | One Linux host, or Docker |
| Database | PostgreSQL 10.23 | Same host or managed — pinned to this exact version; see `backend/requirements.txt` |
| Frontend | Vue, built to static files | Served by the reverse proxy |
| Reverse proxy | nginx or Caddy — terminates TLS | Same host |
| Desktop agent | Windows tray app | Each employee PC |

The agent talks to the backend over HTTPS with a device token. The browser talks to it
with a session cookie. Nothing else is exposed.

---

## 2. Before you start

Decide these, because the defaults are what almost everyone will end up with:

- [ ] **Hostname**, e.g. `office.example.com`, with DNS pointing at the host.
- [ ] **Office coordinates and radius.** The default radius is 200 m. Get the
      coordinates from a map, not from a phone standing in the building.
- [ ] **Office timezone.** Default `Asia/Dhaka`. This decides which calendar date a
      punch belongs to and cannot be changed casually later — historical dates were
      derived with it.
- [ ] **Weekend days.** Default is Friday and Saturday. **Confirm this against the
      actual office** (PLAN.md §9 flags it): most installs will never open the settings
      screen, so the default is the behaviour you get.
- [ ] **Retention window for PC activity.** Default 90 days. Shortening it later
      permanently deletes data and requires an explicit confirmation.
- [ ] **The employee notice.** `docs/employee-privacy-notice.md` is a template. Fill it
      in and distribute it **before** the first agent is installed — README §31 requires
      employees be informed, and doing it afterwards is not the same thing.

---

## 3. Backend

### 3.1 Secrets

Generate a real secret key. The application refuses to start with `DEBUG=false` and a
placeholder value, so this is not an optional step:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Write `/etc/office-management/.env`, owned by the service user, mode `600`:

```ini
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=<the value you just generated>
DJANGO_ALLOWED_HOSTS=office.example.com
DJANGO_CORS_ALLOWED_ORIGINS=https://office.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://office.example.com
DJANGO_LOG_LEVEL=INFO

POSTGRES_DB=office_management
POSTGRES_USER=office
POSTGRES_PASSWORD=<generated, not chosen>
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_CONN_MAX_AGE=60

# First deploy only — see §3.4.
DJANGO_SECURE_HSTS_SECONDS=0
```

`.env` is gitignored and must never be committed. It is also the single most valuable
file on the host: it is the thing to protect and the thing to back up separately from
the database (§4 of `backup-and-restore.md`).

**If the frontend is served from a *different subdomain* than this API** (e.g. frontend
on `app.example.com`, this API on `api.example.com` — as opposed to the single-host
setup this runbook otherwise assumes), add one more line:

```ini
DJANGO_CSRF_COOKIE_DOMAIN=.example.com
```

Without it, `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS` alone are not enough: the
CSRF cookie defaults to the exact host that set it, so the frontend's own JavaScript can
never read it back to echo in the `X-CSRFToken` header, regardless of how correctly
those two are configured — they govern the request, not what a *different* origin's
JavaScript may read afterwards. Login still succeeds either way (DRF only enforces CSRF
once a session exists), so the failure surfaces one request later — logout, or the first
save — looking exactly like a permissions bug rather than a missing setting. See
`backend/config/settings.py`'s comment on `CSRF_COOKIE_DOMAIN` for the full mechanism.

### 3.2 Database and migrations

Use `python3.10` explicitly if the host's default `python3` resolves to something newer
— Django 4.0 is untested (and, per its own compatibility statement, unsupported) on
Python 3.11+, so a newer interpreter here is not a safe substitution even if it happens
to run.

```bash
cd backend
python3.10 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py createsuperuser
```

`createsuperuser` gives you an account that can reach `/admin/`. Create the first
*application* admin through the web app or the Django admin, with role `ADMIN`.

### 3.3 Run it

```bash
gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 3 --access-logfile -
```

Bind to localhost only. The proxy is what faces the network.

A systemd unit, `EnvironmentFile` pointing at the `.env` above:

```ini
[Unit]
Description=Office Management backend
After=network.target postgresql.service

[Service]
User=office
WorkingDirectory=/srv/office-management/backend
EnvironmentFile=/etc/office-management/.env
ExecStart=/srv/office-management/backend/.venv/bin/gunicorn config.wsgi:application \
    --bind 127.0.0.1:8000 --workers 3 --access-logfile -
Restart=always

[Install]
WantedBy=multi-user.target
```

### 3.4 TLS and HSTS **[unverified — needs a real certificate]**

Terminate TLS at the proxy and forward the scheme, which the backend is configured to
trust via `SECURE_PROXY_SSL_HEADER`:

```nginx
server {
    listen 443 ssl http2;
    server_name office.example.com;

    ssl_certificate     /etc/letsencrypt/live/office.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/office.example.com/privkey.pem;

    root /srv/office-management/frontend/dist;
    index index.html;

    location / { try_files $uri $uri/ /index.html; }

    location ~ ^/(api|admin|static)/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;   # required
    }
}

server {
    listen 80;
    server_name office.example.com;
    return 301 https://$host$request_uri;
}
```

**Raise HSTS only after HTTPS is confirmed working.** Deploy first with
`DJANGO_SECURE_HSTS_SECONDS=0`, confirm the site loads over HTTPS and the certificate is
valid, then remove that line so the default one-year value applies and restart. An HSTS
header sent by mistake is cached by every visitor's browser for its full duration and
cannot be withdrawn.

Preload (`DJANGO_SECURE_HSTS_PRELOAD`) stays off unless whoever owns the domain has
decided otherwise; submission to the browsers' preload list is effectively permanent.

### 3.5 Verify the configuration

```bash
DJANGO_DEBUG=false .venv/bin/python manage.py check --deploy --fail-level WARNING
```

This must exit 0. One check, `security.W021` (HSTS preload), is silenced deliberately in
`config/settings.py` with its reason; nothing else is.

Then, from another machine:

```bash
curl -sS https://office.example.com/api/health/     # {"status":"ok","database":"ok"}
curl -sI http://office.example.com/ | head -1       # 301 to https
curl -sI https://office.example.com/api/health/ | grep -i strict-transport
```

---

## 4. Frontend

```bash
cd frontend
npm ci
VITE_API_BASE_URL=https://office.example.com/api npm run build
```

Copy `dist/` to where the proxy serves it. The API base URL is baked in at build time,
so a change of hostname means a rebuild, not a config edit.

---

## 5. Scheduled jobs

Three jobs, none optional. Without them: nobody is ever marked absent, dead PCs show as
online forever, and activity is never deleted — the last of which is a broken promise to
employees, not just a growing table.

```cron
# Close sessions for machines that stopped answering. Every minute.
* * * * * cd /srv/office-management/backend && .venv/bin/python manage.py mark_offline_computers

# Mark yesterday's no-shows absent. After midnight office-local; 02:00 Dhaka = 20:00 UTC.
0 20 * * * cd /srv/office-management/backend && .venv/bin/python manage.py mark_absentees

# Delete activity past the retention window. After the absentee job.
30 20 * * * cd /srv/office-management/backend && .venv/bin/python manage.py purge_activity
```

Cron does not read your `.env`; use `systemd` timers with `EnvironmentFile`, or source it
in the crontab entry. A job that fails silently every night because `DJANGO_SECRET_KEY`
is unset is the failure mode to design against — check the audit log a day after go-live
for an `ACTIVITY_PURGED` entry, which is written on every run including one that deleted
nothing.

Before the first real run:

```bash
.venv/bin/python manage.py purge_activity --dry-run
```

---

## 6. Desktop agent rollout

### 6.1 Build the installer

On a Windows machine, with Python 3.13 and Inno Setup 6:

```powershell
cd desktop-agent
pip install -r requirements-dev.txt
.\installer\build.ps1
```

This runs the privacy guard and the tests before packaging — a binary that was never
checked defeats the point of checking — then produces
`dist\OfficeTrackerSetup-<version>.exe`.

**Signing.** An unsigned installer trips SmartScreen and every user sees a warning. Sign
it if a code-signing certificate is available (`SignTool` in `OfficeTracker.iss`), or use
the IT-managed silent install below, where no user sees the prompt.

### 6.2 Install **[unverified at fleet scale — see the manual matrix in `desktop-agent/README.md`]**

Interactive, on one machine, to check the whole path first:

```
OfficeTrackerSetup-0.1.0.exe
```

Silent, for a managed rollout:

```
OfficeTrackerSetup-0.1.0.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SERVER=https://office.example.com
```

`/SERVER=` writes the backend URL at install time, so each machine then needs only its
enrolment code.

**Autostart requires an interactive user at install time.** The agent must run in a
desktop session to see the foreground window at all, so autostart is a per-user
`HKCU\Run` value, written in the *logged-in* user's hive rather than the elevating
administrator's. A deployment running as `SYSTEM` with nobody logged in installs the
binary but cannot write that value; on those machines, run once as the user:

```
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v OfficeTrackerAgent ^
    /t REG_SZ /d "\"C:\Program Files\OfficeTracker\OfficeTrackerAgent.exe\"" /f
```

### 6.3 Enrol each PC

1. In the web app: **Computers → Enrol computer**, pick the employee, note the code.
2. On the PC, from the tray icon, or:
   ```
   "C:\Program Files\OfficeTracker\OfficeTrackerAgent.exe" --enroll ABCDE-FGHJK
   ```
3. Confirm it appears online on the dashboard within a minute or two.

Codes are single-use. A machine that loses its token needs a new code, not a lookup —
the server stores only a hash.

### 6.4 Support

The build is windowed, so `--status` has no console to print to. Redirect it:

```
"C:\Program Files\OfficeTracker\OfficeTrackerAgent.exe" --status > %TEMP%\agent-status.txt
```

Or read the same information from the tray menu.

### 6.5 Removing a PC

**Disable the computer in the web app first**, then uninstall. In that order, and not the
other way round: disabling revokes the device token server-side, which is the only step
that works regardless of what remains on the machine.

Uninstall then removes the binary, the autostart entry, the local queue (the file holding
that machine's application and website history), the config, and the stored token. If an
administrator uninstalls from a different Windows account than the person who used the
agent, the token stays in that other account's Credential Manager — harmless once the
device is disabled server-side, which is why that step comes first.

---

## 7. Go-live checklist

- [ ] Employee notice distributed, and questions answered, **before** any agent installed
- [ ] `check --deploy --fail-level WARNING` exits 0
- [ ] `/api/health/` returns 200 over HTTPS; HTTP redirects
- [ ] HSTS raised only after the certificate is confirmed
- [ ] Office coordinates, radius, timezone, weekend days and retention set and reviewed
- [ ] An admin account exists and can sign in; a test employee can check in
- [ ] All three cron jobs installed, and their environment verified
- [ ] `purge_activity --dry-run` run and its output understood
- [ ] Backups running, **and a restore tested** (`backup-and-restore.md` §5)
- [ ] Agent installed and enrolled on one machine end to end before the fleet
- [ ] `admin-guide.md` handed to whoever will operate this day to day

---

## 8. Upgrades

```bash
git pull
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
systemctl restart office-management
```

Take a database backup before migrating. Agents tolerate the backend being briefly
unavailable — they queue locally and resend, and nothing is marked synced until the
server confirms it — so a short restart during working hours loses nothing.

Agent upgrades are a re-run of the installer; it stops a running agent first, so an
upgrade does not fail on a locked file.
