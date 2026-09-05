# Phase 1 Spike Report — Windows Activity Capture

Date: 2026-08-19 · Host: Windows 11 Pro 26100 · Python 3.13
Code: `spikes/` (throwaway — deleted once Phases 4–6 land)

Phase 1 exists to answer one question before the schedule is committed: **can the agent
actually capture what §14–16 require?** Answer: **yes on all three browsers**, including
private windows, plus application and idle tracking. No blocking risk remains.

Updated 2026-08-19 after Firefox was installed on the dev host and verified.

---

## Verdict

| Capability | Browser / scope | Result |
|---|---|---|
| Foreground application + executable (§15) | all apps | **Works** |
| Idle / active detection (§14) | session-wide | **Works** |
| Website domain (§16) | **Chrome** | **Works** — normal and incognito |
| Website domain (§16) | **Edge** | **Works** — normal and InPrivate |
| Website domain (§16) | **Firefox 154** | **Works** — normal and private, after a control-type fix |

**Phase 6 proceeds as planned for all three browsers.** 12/12 trials pass.

---

## Spike 1 — Foreground application and idle

`GetForegroundWindow` → `GetWindowThreadProcessId` → `psutil.Process(pid)` returned the
process name and executable path on every sample; `GetLastInputInfo` tracked the idle
timer responsively (0.0–1.2s while typing). Lock detection via `OpenInputDesktop` worked.
Six samples over 12s, zero failures.

Three findings that change the implementation:

1. **Tick counters wrap.** `GetLastInputInfo` and `GetTickCount` are 32-bit millisecond
   counts that roll over about every 49.7 days. A naive subtraction returns a large
   negative idle time on a long-uptime machine — which, on a workstation left running,
   would silently corrupt active/idle totals. The spike masks the subtraction to
   `0xFFFFFFFF`; the production collector must do the same.
2. **`process.exe()` can be denied.** Elevated processes refuse the path to a
   non-elevated caller. `process.name()` still succeeds, and §15 only requires the
   executable name "where available", so the collector degrades rather than failing.
3. **Window titles must not be stored.** The sampler read titles like
   `PLAN.md - Visual Studio Code` and `01-architecture-overview.md - Visual Studio Code`.
   Those are document and file names. Storing them would amount to file-activity
   monitoring, which §31 prohibits. **The collector must capture application name and
   executable only, and discard the title** — with one narrow exception below.

---

## Spike 2 — Website domain capture

Isolated `--user-data-dir` profiles were launched per trial, only the launched PIDs were
scanned, and every process was killed and every temp profile removed afterwards. No real
browsing data was read at any point.

Target `https://example.com/some/path?with=query#and-fragment` → expected `example.com`.

| Browser | Phase | Time | Domain | Result |
|---|---|---|---|---|
| Chrome | cold | 61ms | example.com | PASS |
| Chrome | warm | 53ms | example.com | PASS |
| Chrome (private) | cold | 65ms | example.com | PASS |
| Chrome (private) | warm | 49ms | example.com | PASS |
| Edge | cold | 68ms | example.com | PASS |
| Edge | warm | 54ms | example.com | PASS |
| Edge (private) | cold | 71ms | example.com | PASS |
| Edge (private) | warm | 57ms | example.com | PASS |
| Firefox | cold | 131ms | example.com | PASS |
| Firefox | warm | 110ms | example.com | PASS |
| Firefox (private) | cold | 259ms | example.com | PASS |
| Firefox (private) | warm | 116ms | example.com | PASS |

**Chrome needed no accessibility flag.** The concern that Chrome withholds its UIA tree
until an accessibility client asks did not materialise — the first cold query succeeded
at normal speed. No `--force-renderer-accessibility` required.

**Private/incognito windows are readable** on all three browsers. Confirmed as wanted —
see decision D8.

### Firefox needed a fix, and it was not the one expected

Firefox initially returned "no address bar control found" on every trial. The concern
going in was that its accessibility engine would be dormant and need prefs forcing it on
per profile — which would have been a deployment problem, since it means touching every
employee's Firefox profile. **That is not what was wrong.**

Dumping the UIA tree showed two things:

1. **A fresh throwaway profile opens an onboarding page** that covers the normal browser
   chrome. That is a testing artifact — no real user's profile does this — and it was
   masking the tree.
2. **Firefox exposes its address bar as a `ComboBoxControl` named
   `Search or enter address`, not an `EditControl`.** Searching for an EditControl finds
   nothing at all in Firefox: the tree contains **zero** of them. The original matcher
   looked only for EditControls, so it could never have succeeded.

With the control type corrected, Firefox passes with **no accessibility prefs at all** —
verified by running the diagnosis with and without them and getting an identical tree.
Nothing needs to be changed on an employee's machine.

**Firefox is 2–3× slower to read** (110–259ms vs 47–98ms for Chromium), which makes
title-gated polling more important there, not less.

**Firefox is also slow to become readable after launch.** With a 9s settle it
intermittently returned no window at all; at 20s it is reliable. Production implication:
the collector must treat "browser window present but not yet readable" as a normal
transient state and retry, not record a gap.

---

## Spike 3 — Read cost, and the fix

A UIA address-bar read costs **46.4ms median / 64.9ms max**. On the planned 2s poll that
is **2.32% of a core burned continuously** whenever a browser is focused — too much for
something meant to be invisible in Task Manager.

`GetWindowText` on the same window costs **0.001ms median** — about **42,000× cheaper**.

Since the window title changes on every navigation and every tab switch, the collector
can poll the cheap title and only pay for UIA when the title actually changes:

```
every 2s:
    title = GetWindowText(foreground_hwnd)        # ~0.001ms
    if title != last_title_for_this_window:
        domain = uia_read_address_bar(...)        # ~46ms, only on change
```

This turns a continuous 2.32% cost into a per-navigation one, roughly **0.0001% steady
state**. The title is used **only** as a change signal and is never stored — which keeps
finding 3 above intact.

Residual risk: a single-page app that changes URL without changing the title would be
missed until the next title change. Acceptable — domain-level tracking means an in-site
navigation usually keeps the same domain anyway.

---

## Privacy boundary

`extract_domain` was unit-tested against 22 synthetic cases before any browser was
touched (`spikes/test_extract_domain.py`, 22/22 pass). Verified discarded: paths, query
strings, tokens, fragments, embedded credentials, ports. Verified rejected: search
queries, `chrome://` and `edge://` internals, `about:blank`, `file:///` paths,
`view-source:`, `data:` URLs, bare words, single-label hosts. Verified normalised: case
folding and `www.` stripping so `WWW.Google.com` and `google.com` aggregate together.

These assertions move into the Phase 6 production test suite unchanged.

**One tooling note.** `uiautomation` is dual-use: it can also synthesise input and grab
bitmaps. `scripts/check_privacy.py` does not ban it, because address-bar reading is
impossible without it. The agent must use only its tree-reading APIs. Consider a
narrower guard in Phase 6 that rejects `uiautomation`'s input and bitmap calls
specifically, so the capability stays unavailable in practice.

---

## Impact on the plan

Nothing in `PLAN.md` needs restructuring. Six amendments:

1. **Phase 6 confidence rises from "risky" to "known"** on all three browsers. The
   browser-capture risk is retired; only "a future browser update breaks the UIA names"
   remains, and that is a maintenance risk, not a design one.
2. **Title-gated polling** becomes part of the Phase 6 design, not an optimisation to
   consider later. It is what makes the 2s poll affordable, and Firefox's 2–3× slower
   reads make it more necessary there.
3. **Match on control type, not just name.** Chromium exposes an `EditControl`; Firefox
   exposes a `ComboBoxControl`. A name-only matcher silently finds nothing on Firefox.
4. **Tick-wrap masking** is a required detail of the Phase 5 idle collector.
5. **"Never store window titles"** joins the §6 guardrails as an explicit rule, alongside
   the existing domain-only rule.
6. **"Not yet readable" is a normal state.** A browser window can exist for many seconds
   before its UIA tree is queryable. The collector retries rather than recording a gap.

---

## Decisions taken

Both open questions were answered on 2026-08-19:

1. **Firefox — verified.** Installed on the dev host and confirmed working (Firefox 154).
   Supported in the MVP alongside Chrome and Edge.
2. **Private browsing — tracked (D8).** Incognito, InPrivate and Firefox private windows
   are all readable and **will be recorded**, with no distinction from normal browsing.
   This is a deliberate policy choice, so it carries an obligation: the employee notice
   §31 requires must state plainly that private browsing is tracked too. Employees
   generally assume the opposite, and an unstated exception here is the kind of thing
   that turns a legitimate monitoring programme into a grievance.

## Harness bug worth recording

The first cleanup pass left **93 Firefox processes running and 704MB of temp profiles**
on disk. Cause: Firefox's launcher process re-execs and exits, so the PID returned by
`Popen` is dead within seconds and owns no children — killing its "tree" killed nothing.
`shutil.rmtree(..., ignore_errors=True)` then swallowed every locked-file error silently.

Fixed in the spike harness by tracking the profile path as the authoritative marker and
retrying deletion with the final attempt raising. The general lesson applies to the
production agent: **on Windows, a process tree rooted at a launched PID is not a reliable
handle on what that launch actually started**, and silent error suppression around
cleanup hides exactly the failures worth knowing about.
