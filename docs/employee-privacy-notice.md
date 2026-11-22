# Employee notice: what this system records

*Template. The organisation must review this, fill in the bracketed details, and give it
to every employee **before** tracking starts. README.txt §31 requires that employees are
informed; handing someone a laptop with a tracking agent already on it and no notice does
not meet that requirement, whatever the software does.*

*This version adds screenshot capture, which an earlier version of this notice told
employees would never happen ("Ever, including on request"). If any employee already
received that earlier version, this is not a quiet amendment to hand out at the next
all-hands — re-issue it individually, call out explicitly that this is a reversal of
that specific earlier promise, and get a positive acknowledgment from each employee
before enabling screenshot capture for them. [SCREENSHOTS APPROVED BY / DATE] should
record who made this decision and when.*

---

## In short

Three things are recorded: **when you check in and out, and where you were when you
did**, **what your work PC was doing while the agent was running**, and, as of
[DATE SCREENSHOTS ENABLED], **periodic screenshots of your screen while the agent is
running**. Screenshots are the one item on this list that you cannot see yourself —
see "Who can see it" below.

The list below of what is *not* recorded is not a promise about intent. It describes
what the software is built to be incapable of: those capabilities are absent from the
code, and an automated check refuses to build a release that adds any of them.
Screenshot capture is a deliberate, named exception to that list, added on the date
above — every other item below is still enforced the same way it always was.

---

## What is recorded

### Attendance

| Recorded | Detail |
|---|---|
| Check-in and check-out times | To the minute, in [OFFICE TIMEZONE] |
| Location at the moment you check in or out | Latitude and longitude, how accurate your phone said that reading was, and how far it is from the office |
| Whether you were inside or outside the office area | A [RADIUS] m circle around [OFFICE ADDRESS] |
| Lateness | Minutes after your scheduled start |
| Leave and holidays | Days taken and remaining |

**Location is captured only at the instant you press check in or check out.** There is no
background location tracking, and the system cannot see where you are at any other time —
including during the working day, at lunch, or after hours.

Phone GPS indoors is commonly accurate to only 30–100 m. Being recorded as outside the
office area is not treated as an accusation: the distance and the accuracy figure are
stored together so that a manager reviewing it can see the difference between "across
town" and "GPS was vague today".

### PC activity

Recorded only while the agent is running on your work PC:

| Recorded | Example |
|---|---|
| When the PC was on | 09:01–18:04 |
| Whether you were active or idle at it | Idle after [IDLE THRESHOLD] minutes without keyboard or mouse |
| Which application was in the foreground | `Google Chrome`, `Visual Studio Code`, `Microsoft Excel` |
| The domain of the website in the foreground browser tab | `github.com` |

### Screenshots

*Added [DATE SCREENSHOTS ENABLED]. This is a materially different and more sensitive
capability than the rest of PC activity above, and is called out in its own section
rather than folded into the table, on purpose.*

| Recorded | Detail |
|---|---|
| A screenshot of your screen | Taken periodically while the agent is running, at [SCREENSHOT INTERVAL] |
| How long it is kept | [SCREENSHOT RETENTION DAYS] days, deleted on its own schedule — not the same [RETENTION DAYS]-day schedule as the rest of PC activity |
| Who can view it | [WHICH ROLES] only. **Not you.** Every other item this system records about you, you can see yourself at [SYSTEM URL]/my; a captured screenshot is the one exception — you cannot see the image itself. |
| What you can see instead | Whether a screenshot of yours has been viewed, by whom, and when — this is logged every time, with no exceptions, and shown back to you at [SYSTEM URL]/my |
| Before anyone views it | Each screenshot goes through a review/redaction step first. Nobody — including an administrator — can open a screenshot that hasn't cleared that step. |

---

## What is **not** recorded

- **Keystrokes.** No keylogging of any kind.
- **Screen recording (video).** Only still screenshots, per above — not continuous
  recording.
- **Webcam or microphone.**
- **Clipboard contents.**
- **Window titles.** The title bar names the document, spreadsheet or message you have
  open. It is read momentarily as a signal that you switched windows and is discarded
  immediately; it is never stored or transmitted.
- **Full web addresses.** Only the domain. `github.com` is recorded; the page, the
  repository, the search terms and anything after the domain are not, and are discarded
  inside the agent before anything is written to disk or sent over the network.
- **Private browsing is not exempt from the domain record**, but it is not treated
  differently either — the same domain-only rule applies.
- **File contents, file names, or which files you opened.**
- **Email, chat or private message content.**
- **Passwords.** The system never sees them.
- **Your location outside of the check-in and check-out moments.**

---

## Where the data goes and how long it stays

- It is stored on [SERVER LOCATION / HOSTING], reachable only over an encrypted (HTTPS)
  connection.
- **PC activity is deleted automatically after [RETENTION DAYS] days** (the default is
  90). This is a scheduled job, not a manual clear-out, and every run is logged.
- **Screenshots are deleted automatically after [SCREENSHOT RETENTION DAYS] days**, on
  their own separate schedule from the rest of PC activity, for the same reason: a
  scheduled, logged job, not a manual clear-out.
- **Attendance and leave records are kept**, because they are employment records rather
  than activity monitoring. They are not covered by the automatic deletion above.
- Administrative actions — changing your record, correcting attendance, exporting
  reports — are written to an audit log showing who did what and when.

## Who can see it

- **You** can see all of your own data, at any time, at [SYSTEM URL]/my — the same
  numbers your manager sees, not a summary. **The one exception is screenshots**: you
  can see that one was captured, and a log of who viewed it and when, but not the image
  itself.
- **[WHICH ROLES — e.g. HR and your line manager]** can see the whole workforce's
  attendance and activity, and can export it. For screenshots specifically, every view
  is logged, with no exceptions — including for the above roles.
- Other employees cannot see your data. The system refuses the request rather than
  quietly returning something else.

## What you can do

- **See your own record.** Sign in at [SYSTEM URL] and open *My dashboard*.
- **Ask for a correction.** If a check-in time or an attendance day is wrong, contact
  [CONTACT]. Corrections are made by an administrator and recorded in the audit log with
  a note.
- **Close the agent.** It is a tray application, not a locked-down service, and you can
  quit it from the tray icon. Doing so leaves a visible gap in the record rather than
  hiding anything, so tell [CONTACT] if you need to — but the choice is deliberately
  yours rather than enforced by the software.
- **Ask questions.** [CONTACT / DATA PROTECTION CONTACT].

---

*Questions about this notice, or about data the system holds on you: [CONTACT].*
*Last reviewed: [DATE].*
