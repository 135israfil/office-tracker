# Desktop Agent

Windows tray application that reports PC activity to the backend. Phases 4-6 are
implemented: registration, liveness, activity sessions, offline sync and website
domains. See `claudedocs/PLAN.md` sections 4 and 5 for the module layout and the
reasoning behind the user-session tray model (decision D3).

## Hard constraints

Per `README.txt` section 31, this agent must never gain the ability to capture
keystrokes, screens, webcam, microphone or clipboard. `scripts/check_privacy.py`
enforces that in CI and rejects the relevant imports outright.

Website tracking stores the **domain only** - never a full URL. The truncation happens
inside the collector, before anything is written to disk or sent over the network.

## Layout

```
agent/
  main.py             CLI, thread wiring, single-instance lock
  service.py          enrolment, heartbeat loop, lifecycle reporting
  api.py              HTTP client for /api/agent/*, timeouts and backoff
  config.py           agent.json in %PROGRAMDATA%, token in Credential Manager
  machine.py          computer name, OS name, agent version
  single_instance.py  lock file so autostart plus a manual launch is still one agent
  tray.py             tray icon, status and enrolment dialogs
  sessions.py         samples -> closed sessions, with the rules that end them
  collectors/
    idle.py           GetLastInputInfo, tick-wrap safe
    application.py    foreground app; window title read as a signal, never stored
    browser.py        foreground tab domain via UI Automation, title-gated
    system.py         startup/shutdown/sleep/wake/lock via window messages
  storage/
    queue.py          SQLite buffer; synced only after a 2xx
  sync/
    client.py         batched upload, backoff, drop what the server refuses
```

## Running it

```bash
pip install -r requirements-dev.txt

python -m agent --server https://office.example.com --enroll ABCDE-FGHJK
python -m agent                  # tray app; this is what autostart runs
python -m agent --status         # what to ask for first when something looks wrong
python -m agent --headless       # no tray, for a test box or a smoke check
```

`OFFICE_AGENT_DATA_DIR` overrides where `agent.json` lives, which is how tests and dev
runs avoid touching a real installation.

## How enrolment works

1. An admin creates the computer in the web app (Computers → Enrol computer) and reads
   out the one-time code. It expires in seven days and works exactly once.
2. `--enroll` (or the tray menu) exchanges the code for a device token.
3. The token goes straight into Windows Credential Manager. It is never written to
   `agent.json`, and there is no disk fallback: if the credential store is unavailable
   the agent fails loudly rather than leaving a token in a text file.
4. A lost token means a new code from an admin, not a lookup — the server keeps only a
   SHA-256 hash.

## What it collects

Three loops run independently, so an outage cannot stop collection and a stuck collector
cannot stop liveness:

| Loop | Interval | Job |
|------|----------|-----|
| heartbeat | 60s (server-configured) | liveness and PC-on sessions |
| sampler | 2s | reads idle state and foreground app, builds sessions |
| sync | 60s (server-configured) | drains the local queue |

The sampler produces **sessions, not samples** (§18). A session ends when the value
changes, when the state goes idle, at a hard 15-minute cap, or when a gap in the samples
means nothing was observed — that last one closes at the *last sample*, not at the
resumption, so a laptop that slept through lunch does not report lunch as work.

Idle closes the application track. Otherwise a PC left on overnight with an editor
focused would report eight hours of using it.

### Websites (§16, §17)

Chrome, Edge and Firefox, normal and private windows alike (decision D8 — and the
employee notice must say so, because people assume private browsing is exempt). Only the
**foreground** window is ever consulted.

What leaves `collectors/browser.py` is a bare host or nothing:

```
https://example.com/private/account?id=123&token=xxxxx   ->  example.com
https://user:pw@intranet.example.com:8443/hr/pay.xlsx    ->  intranet.example.com
chrome://settings  ·  file:///C:/tax.pdf  ·  "how to..."  ->  nothing at all
```

The full string exists only as a local variable inside one function. The exhaustive case
list is in `tests/test_browser.py` rather than in a comment, because that is the form
that fails the build when someone breaks it.

Reading the address bar costs 46-259ms (the Phase 1 spike measured it), so it happens
only when the window title changes — the title read that gates it costs 0.001ms. That is
the difference between 2.3% of a core and effectively nothing.

Everything is written to `queue.sqlite3` before any upload is attempted, and marked
synced only after the server answers 2xx. A dropped response therefore means the batch is
sent again — which is safe, because the server upserts on `client_event_id` and counts
the second copy as a duplicate.

## Liveness and lifecycle events

One heartbeat per interval (server-configured, default 60s) carrying the current state
(`ONLINE` or `IDLE`, from the server-configured idle threshold) and, when something
happens, one lifecycle event: `STARTUP`, `SHUTDOWN`, `SLEEP`, `WAKE`, `LOCK`, `UNLOCK`.
The server turns those into PC-on sessions.

Two things are worth knowing because they look like bugs otherwise:

- **`STARTUP` is sent as the first heartbeat of a run, not by the system collector.**
  It is a fact about the process, and emitting it from the message pump raced the
  heartbeat thread: whichever arrived first refreshed "last seen", and the session the
  previous run abandoned then swallowed the downtime it was supposed to be closed
  before. Found while verifying against a live server, not in a unit test.
- **A reported shutdown is a nicety, not the mechanism.** Power cuts and crashes send
  nothing, so the server closes open sessions after three missed heartbeats, at the last
  heartbeat time. The agent's shutdown notice only makes the timestamp more precise.

## Tests

```bash
pytest -q          # runs anywhere; win32 calls sit behind pure functions
ruff check .
black --check .
```

CI runs these on Linux. Everything platform-specific — the actual UIA/window-message
paths — is covered by the manual matrix below.

### Manual matrix (real Windows 10 and 11)

Run before releasing an agent build. None of this can be automated honestly.

| Scenario | Expected |
|----------|----------|
| Install and enrol with a fresh code | Tray icon green, computer shows ONLINE within one interval |
| Enrol with an expired or reused code | Clear refusal, no token stored |
| Autostart after reboot | Agent runs, `STARTUP` closes the previous session at its last heartbeat |
| Launch a second copy | Second exits with "already running", no duplicate heartbeats |
| Lock and unlock the workstation | `LOCK` / `UNLOCK` reported, session stays open |
| Sleep and wake | Session closes on `SLEEP`, a new one opens on `WAKE` |
| Shut down from the Start menu | `SHUTDOWN` reported, session closed at that moment |
| Pull the network cable for 5 minutes | Heartbeats back off; computer goes OFFLINE; recovery reopens a session |
| Kill the process from Task Manager | Computer goes OFFLINE after three missed heartbeats, session closed at the last one |
| Disable the device in the web app | Agent gets 401, clears its token, tray turns amber |
| Idle for longer than the threshold | Status shows IDLE, then ONLINE again on the next input |
| Leave running overnight on battery | No measurable CPU in Task Manager, no log growth beyond a few KB |
| Work normally for an hour | Sessions match what you actually used; no window titles anywhere in the data |
| Pull the network cable mid-session | Sessions keep accruing locally; `--status` shows a rising pending count |
| Reconnect after an outage | Queue drains in batches; the server reports duplicates, not new rows, on any replay |
| Kill the agent mid-session and restart | At most the open 15-minute session is lost; the queue resumes from disk |
| Sleep the laptop for an hour mid-session | The open session ends at the last sample, not at wake |
| Browse in Chrome, Edge and Firefox | Domains appear for each; check the stored rows contain no paths or queries |
| Browse in an incognito / private window | Tracked the same as normal (D8) — this is intended, and disclosed |
| Type a search into the address bar | No website session for the query text |
| Open `chrome://settings` or a local file | No website session at all |
| Switch tabs rapidly for a minute | Sessions follow the foreground tab; CPU stays flat in Task Manager |
| Launch a browser and read immediately | The first seconds may be unreadable; no gap appears in the data |
