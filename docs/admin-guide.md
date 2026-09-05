# Administrator guide

For whoever runs this day to day — HR, an office manager, whoever ends up with the admin
account. It assumes no knowledge of how the system is built.

Deployment and servers are in `deployment-runbook.md`. This is about using it.

---

## The short version

| You want to | Go to |
|---|---|
| See who is in today | **Dashboard** |
| Look at one person's day in detail | **Activity** |
| Fix a wrong check-in time | **All attendance** → the day → *punches* |
| Add someone | **Employees** → *Add employee* |
| Record leave | **All attendance** → *Mark leave* |
| Get a spreadsheet | **Reports** → filter → *Export CSV / Excel* |
| Set up a new PC | **Computers** → *Enrol computer* |
| Change office hours, weekend, retention | **Settings** |

---

## 1. Reading the dashboard

Two panels, and the counts mean specific things.

**Today's attendance.** Present, Late, Absent, Leave — and **Not recorded**, which is
separate on purpose. At 10am, someone with no row has simply not arrived yet. The system
does not call that absent, because for most of the working day it would be wrong.
Absences are worked out overnight by a scheduled job.

**PC status.** *Online* is the total that are answering; it splits into *Active* and
*Idle*, so 39 online means 34 active and 5 idle rather than a fourth separate number.
*Offline* means three heartbeats missed — roughly three minutes of silence — not
necessarily a machine that was shut down properly.

A machine that loses power sends no shutdown notice, so its session is closed at the last
heartbeat it did send. The timeline says "PC stopped responding" for that, and "PC
shutdown" when the agent reported going down. They are different events and are not
merged.

---

## 2. Employees

**Add:** Employees → *Add employee*. Employee ID, name, department, designation, joining
date, leave allowance, and a shift. Everyone gets a default 09:00–18:00 shift unless you
set otherwise.

**Split shifts** (two windows in a day, e.g. 09:00–13:00 and 15:00–19:00) must be enabled
in Settings first. With them on, someone can check in and out more than once a day and
each pair is matched to the shift it belongs to.

**Leaving:** *Disable*, do not delete. Disabling stops them signing in and takes them off
today's roster while keeping their history, which is what payroll and any later query
need. Reports can include disabled employees with the *include inactive* option, so last
quarter's numbers do not change when somebody is offboarded.

**Leave balance:** Employees → *Leave adjustments*. Every adjustment records who made it
and why.

---

## 3. Attendance

### Reviewing

**All attendance** lists everyone's days with filters for employee, department, date,
range and status. A row flagged **needs review** means the system could not confidently
match a punch to a shift and stored it rather than guessing — usually an extra check-in
on a split-shift day. Look, decide, correct if needed.

### Check-in location

Each check-in records where the phone said it was, how far that is from the office, and
**how accurate the phone claimed to be**. Read those together. Indoor GPS is commonly
accurate to 30–100 m, so:

- 40 m away, accuracy 15 m → they were at the office.
- 800 m away, accuracy 20 m → they were not.
- 300 m away, accuracy 200 m → the phone did not know. This is not evidence.

Being outside the radius is flagged, never blocked. Someone visiting a client can still
check in, and you can see that they did.

### Corrections

All attendance → open the day → edit the punch. Give a reason; it is stored with the
change. Lateness is recalculated against the schedule that was in force **at the time**,
not today's, so correcting an old day cannot retroactively apply a schedule change made
since.

Corrected days are marked as adjusted, with who did it.

### Leave

*Mark leave* on a date. Half-days are available if enabled in Settings. Leave is never
deleted by the retention job.

---

## 4. PC activity

**Activity** shows one employee's day: PC on time, active, idle, top applications, top
websites, and a timeline of what happened when.

Two things worth understanding, because they look like bugs otherwise:

**The numbers do not add up, and should not.** "Active", "application" and "website" time
run in parallel — you can be active, in Chrome, on github.com, all in the same minute.
Adding them produces a number that means nothing. Only compare like with like.

**A PC left on overnight is split across dates.** On from 22:00 to 02:00 gives two hours
to each day, not four to one. Every screen uses that same rule, so the dashboard, the
activity page and the reports always agree.

**Only the domain of a website is recorded** — `github.com`, never the page. That is a
deliberate limit (README §17), not missing data, and the full address is discarded on the
PC before anything is sent.

**Window titles are never recorded**, so you cannot see which document someone had open.
Also deliberate.

---

## 5. Reports and exports

**Reports** has two: attendance and PC activity.

- Filter by date or date range, employee, department, and status.
- PC activity can be grouped by **day** (a row per person per day) or by **employee**
  (one row totalling the range).
- **Export CSV** or **Export Excel**. Exports cover the **whole filtered range**, not
  just the page on screen.

Use **Excel** when you want to sum a column — durations are real durations there, so
`SUM` works on PC time. Use **CSV** for a very long range, or for feeding another system.

Times in exports are in the office timezone, whichever country you run the export from.

Attendance exports include a row per punch for split-shift days. **Worked time is not
last-check-out minus first-check-in**: a day with a two-hour break shows 8 hours worked
against a 10-hour span, and the worked figure is the one to use.

Every export is recorded in the audit log with who, when, the filters and how many rows.
This is a whole workforce's movements leaving in a file; treat the file accordingly.

---

## 6. Computers

**Enrol:** Computers → *Enrol computer* → choose the employee → note the code. On the PC,
enter it in the agent's tray menu. Codes are single-use and short-lived.

**Lost token:** issue a new code. There is no way to look one up — the server keeps only
a hash, deliberately.

**Someone leaves, or a PC is reassigned:** *Disable* the computer **before** the agent is
uninstalled. Disabling is what actually stops that machine reporting; uninstalling only
removes the software. In that order.

**Stop the whole fleet collecting:** Settings → turn off *agent enabled*. Every agent
stops collecting at its next check-in, within a minute or two, without anyone touching a
PC. They keep reporting that they are alive, so you can switch it back on the same way.
This is the control to use if something is wrong and you need collection to stop now.

---

## 7. Settings

Most installs never open this screen, so what is here on day one is what you get.

| Setting | Notes |
|---|---|
| Office name, coordinates, radius | Default radius 200 m. Coordinates from a map, not a phone in the building |
| Timezone | Decides which date a punch belongs to. **Do not change casually** — past dates were worked out with the old value |
| Default start and end time | Applies to employees without their own shift |
| **Weekend days** | Default Friday and Saturday. **Check this matches the office** — it decides who gets marked absent |
| Split shifts | Off by default. On = more than one check-in per day |
| Half-day leave | Off by default |
| Idle threshold | Default 5 minutes without keyboard or mouse |
| Heartbeat / sync intervals | Leave alone unless there is a reason |
| **Agent enabled** | The fleet off-switch. See §6 |
| **Activity retention days** | Default 90. See below |

**Retention.** PC activity older than this is deleted automatically, every night. This is
the number in your employee notice, so the two must match.

Increasing it is unremarkable. **Decreasing it permanently destroys data** — the system
asks you to confirm, and that confirmation is the last chance. There is a minimum of 7
days that cannot be set below.

Attendance and leave are never touched by retention. They are employment records.

---

## 8. The audit log

Every administrative change is recorded: employee edits, attendance corrections, leave
adjustments, settings changes, device enrolment and disabling, report exports, and every
run of the retention job.

It is in the Django admin at `/admin/` under **Audit logs**, filterable by who and when.
It is append-only — the application never edits or deletes an entry.

Nightly retention runs appear as `ACTIVITY_PURGED` with the cutoff and how many rows
went, **including runs that deleted nothing**. If you look one morning and there is no
entry from last night, the job did not run — that is a system problem to report, not a
quiet week.

---

## 9. Things that go wrong

**"Someone's PC shows offline but they're at their desk."** The agent is a tray app and
can be closed. Ask them to check the tray icon. If it is running, check the machine can
reach the server.

**"An employee can't check in — it says they're outside the office."** They can still
check in; it is flagged, not blocked. If it happens to everyone, the office coordinates
or the radius are wrong. If it happens to one person indoors, it is GPS accuracy — check
the accuracy figure on the record.

**"The activity page is empty for a whole day."** Either the agent was not running, or
the fleet kill switch is off (Settings → agent enabled), or the machine was never
enrolled. The Computers page distinguishes these.

**"Nobody was marked absent yesterday."** The overnight job did not run. Report it —
`deployment-runbook.md` §5 covers the scheduled jobs.

**"The numbers in the report don't match the dashboard."** They should, and they are
computed by the same code. Check you are comparing the same date range and the same
metric, and that you are not adding activity types together (§4).

**"An export is missing people."** Employees with no record for that day produce no row.
Disabled employees are excluded unless you tick *include inactive*.

---

## 10. What this system deliberately cannot do

Worth knowing before someone asks you for it:

- No keystroke logging, screenshots, screen recording, webcam, microphone or clipboard
  access. These are not switched off; the capability is absent, and an automated check
  refuses to build a release that adds any of them.
- No full web addresses. Domains only.
- No window titles, file names or file contents.
- No location tracking outside the moment of check-in and check-out.

If you are asked for any of these, the answer is that the system cannot do it — and
`docs/employee-privacy-notice.md` is what employees were told, which is the more important
reason.
