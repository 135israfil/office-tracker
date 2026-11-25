"""Turning activity sessions into the numbers the dashboards show (§22, §23).

Two rules shape everything here, and both are about not lying:

**Sessions are clipped to the day.** A PC left on from 22:00 to 02:00 contributes two
hours to each date, not four to one of them. The stored `duration_seconds` is the length
of the session; a day view needs the length of its overlap with that day, which is a
different number and the one people actually check against a timesheet.

**Nothing sums across activity types** that run in parallel. ACTIVE/IDLE, APPLICATION
and WEBSITE sessions routinely cover the same wall-clock minute (§18); adding "active
time" to "application time" would produce a number that means nothing. The one
exception is ACTIVE and IDLE themselves: they are the two mutually exclusive values of
a single state track (never both open at once — see the agent's SessionBuilder), not
two parallel tracks, so `summarise()`'s "PC on" total is their sum, not a separate
heartbeat-derived figure — see that function for why.

The pure functions take plain objects and are exhaustively tested; the ORM layer at the
bottom is the thin part.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from django.db.models import Q
from django.utils import timezone

from attendance.models import AppSettings

from .models import Activity, ActivityType

# How many rows §22's "Top Applications" and "Top Websites" lists show before the rest
# is folded into an "other" bucket. Five matches the README's example and keeps the
# payload small; the bucket exists so the totals still add up.
TOP_N = 5

# A day's timeline can run to thousands of app switches on a busy machine. §23 is a
# human-readable narrative, not an audit log, so it is capped — and the response says
# how many entries were dropped rather than pretending it is complete.
MAX_TIMELINE_ENTRIES = 200

MINUTES_PER_DAY = 24 * 60


def day_window(day: dt.date, settings_obj=None) -> tuple[dt.datetime, dt.datetime]:
    """The UTC instants bounding one office-local calendar day.

    The office timezone is application data (PLAN.md A1), so this is the only place that
    decides where a "day" starts — the same rule attendance uses to decide which date a
    punch belongs to.
    """
    settings_obj = settings_obj or AppSettings.load()
    office = ZoneInfo(settings_obj.timezone)
    start_local = dt.datetime.combine(day, dt.time.min, tzinfo=office)
    end_local = start_local + dt.timedelta(days=1)
    return start_local.astimezone(dt.timezone.utc), end_local.astimezone(dt.timezone.utc)


def overlap_seconds(session, window_start, window_end, now=None) -> int:
    """How much of a session falls inside the window.

    An open session (no `end_time`) is counted up to now, or to the end of the window if
    the window is in the past — an unclosed session from last Tuesday must not keep
    growing every time somebody loads a report.
    """
    now = now or timezone.now()
    start = max(session.start_time, window_start)
    end = session.end_time or min(now, window_end)
    end = min(end, window_end)
    if end <= start:
        return 0
    return int((end - start).total_seconds())


def _bucket(sessions, key, window_start, window_end, now) -> list[dict]:
    totals: dict[str, int] = {}
    for session in sessions:
        label = (getattr(session, key) or "").strip()
        if not label:
            continue
        seconds = overlap_seconds(session, window_start, window_end, now)
        if seconds:
            totals[label] = totals.get(label, 0) + seconds

    ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    top = [{"name": name, "seconds": seconds} for name, seconds in ranked[:TOP_N]]
    other = sum(seconds for _, seconds in ranked[TOP_N:])
    return top, other


def summarise(sessions, window_start, window_end, now=None) -> dict:
    """The §22 numbers for one employee on one day."""
    now = now or timezone.now()

    by_type: dict[str, list] = {}
    for session in sessions:
        by_type.setdefault(session.activity_type, []).append(session)

    def total(activity_type):
        return sum(
            overlap_seconds(session, window_start, window_end, now)
            for session in by_type.get(activity_type, [])
        )

    top_applications, other_application_seconds = _bucket(
        by_type.get(ActivityType.APPLICATION, []), "application_name", window_start, window_end, now
    )
    top_websites, other_website_seconds = _bucket(
        by_type.get(ActivityType.WEBSITE, []), "website_domain", window_start, window_end, now
    )

    active_seconds = total(ActivityType.ACTIVE)
    idle_seconds = total(ActivityType.IDLE)

    return {
        # Deliberately not total(ActivityType.PC_ON): a heartbeat confirms the machine
        # was reachable, but says nothing about whether the sampler was actually
        # producing ACTIVE/IDLE readings at the same moment (it runs in a separate
        # thread, against flakier OS collectors, and closes its own sessions out on any
        # gap — see sessions.py's rule 4). Reporting raw PC_ON time let "on" cover
        # stretches with no corroborating sample at all. ACTIVE and IDLE are the two
        # mutually exclusive values of that one sampler-confirmed state (never both at
        # once, by construction in the agent's SessionBuilder), so summing them is not
        # the cross-type sum this module's docstring warns against — it is the
        # definition of "no data for a timeframe means off".
        "pc_on_seconds": active_seconds + idle_seconds,
        "active_seconds": active_seconds,
        "idle_seconds": idle_seconds,
        "top_applications": top_applications,
        "other_application_seconds": other_application_seconds,
        "top_websites": top_websites,
        "other_website_seconds": other_website_seconds,
        "session_count": len(sessions),
    }


def minute_buckets(sessions, window_start, window_end, now=None) -> list[str]:
    """A one-letter state per minute of the day, for the activity-page strip.

    "O" (off), "A" (active), "I" (idle) — painted in that order, so ACTIVE/IDLE always
    wins over PC_ON's own bare "on" baseline, and a minute no PC_ON session reaches stays
    "O" too: the UI only draws these three states, so "on but unaccounted for" and
    "off" would be indistinguishable anyway.
    """
    now = now or timezone.now()
    buckets = ["O"] * MINUTES_PER_DAY

    def paint(session_list, code):
        for entry in session_list:
            start = max(entry.start_time, window_start)
            end = min(entry.end_time or now, window_end)
            if end <= start:
                continue
            first = int((start - window_start).total_seconds() // 60)
            # -1 second before dividing makes the end exclusive: a session ending
            # exactly on a minute boundary must not also paint that next minute.
            last = int((end - window_start).total_seconds() - 1) // 60
            for minute in range(max(first, 0), min(last, MINUTES_PER_DAY - 1) + 1):
                buckets[minute] = code

    by_type: dict[str, list] = {}
    for session in sessions:
        by_type.setdefault(session.activity_type, []).append(session)

    paint(by_type.get(ActivityType.PC_ON, []), "O")
    paint(by_type.get(ActivityType.ACTIVE, []), "A")
    paint(by_type.get(ActivityType.IDLE, []), "I")
    return buckets


def build_timeline(sessions, window_start, window_end, now=None) -> dict:
    """The §23 narrative: what happened, in order.

    Application entries carry the domain that was open at the time — §23's
    "09:05 - Chrome / github.com" — by looking for a website session covering the same
    instant, which is exactly what the parallel-track model makes possible.
    """
    now = now or timezone.now()
    websites = [s for s in sessions if s.activity_type == ActivityType.WEBSITE]

    def domain_at(instant):
        for website in websites:
            end = website.end_time or now
            if website.start_time <= instant < end:
                return website.website_domain
        return ""

    entries = []
    for session in sessions:
        if overlap_seconds(session, window_start, window_end, now) <= 0:
            continue
        start = max(session.start_time, window_start)

        if session.activity_type == ActivityType.PC_ON:
            entries.append({"at": start, "kind": "PC_ON", "label": "PC started", "detail": ""})
            if session.end_time and window_start <= session.end_time <= window_end:
                entries.append(
                    {
                        "at": session.end_time,
                        "kind": "PC_OFF",
                        # A machine that stopped answering is not the same event as one
                        # somebody shut down, and the timeline should not claim it is.
                        "label": (
                            "PC stopped responding" if session.closed_by_server else "PC shutdown"
                        ),
                        "detail": "",
                    }
                )
        elif session.activity_type == ActivityType.IDLE:
            entries.append({"at": start, "kind": "IDLE", "label": "Idle", "detail": ""})
        elif session.activity_type == ActivityType.APPLICATION:
            entries.append(
                {
                    "at": start,
                    "kind": "APPLICATION",
                    "label": session.application_name,
                    "detail": domain_at(session.start_time),
                }
            )

    entries.sort(key=lambda entry: (entry["at"], entry["kind"]))
    truncated = max(0, len(entries) - MAX_TIMELINE_ENTRIES)
    return {"entries": entries[:MAX_TIMELINE_ENTRIES], "truncated": truncated}


# --- ORM layer --------------------------------------------------------------


def sessions_for_day(employee, day: dt.date, settings_obj=None, device_type=None):
    """Every session overlapping one office-local day, open ones included.

    The filter is an overlap test, not a start-time test: a session that began before
    midnight is part of this day too, and dropping it would lose the first hours of an
    early shift.

    `device_type` (PC/ANDROID, see computers.models.DeviceType) narrows to sessions from
    that kind of device only — used to build the Activity page's separate PC and Phone
    blocks without summing device types together (same "nothing sums across tracks that
    run in parallel" rule above, just applied across devices instead of activity types).
    """
    window_start, window_end = day_window(day, settings_obj)
    queryset = Activity.objects.filter(employee=employee)
    if device_type is not None:
        queryset = queryset.filter(computer__device_type=device_type)
    return list(
        queryset.filter(start_time__lt=window_end)
        # Open sessions have no end and therefore always qualify.
        .filter(Q(end_time__gte=window_start) | Q(end_time__isnull=True))
        .select_related("computer")
        .order_by("start_time", "id")
    )


def activity_day(employee, day: dt.date, settings_obj=None, now=None, device_type=None) -> dict:
    """Everything §22 needs for one employee on one day."""
    settings_obj = settings_obj or AppSettings.load()
    window_start, window_end = day_window(day, settings_obj)
    sessions = sessions_for_day(employee, day, settings_obj, device_type=device_type)

    summary = summarise(sessions, window_start, window_end, now)
    summary["timeline"] = build_timeline(sessions, window_start, window_end, now)
    summary["minute_buckets"] = minute_buckets(sessions, window_start, window_end, now)
    summary["date"] = day
    return summary
