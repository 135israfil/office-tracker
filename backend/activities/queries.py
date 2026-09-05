"""Turning activity sessions into the numbers the dashboards show (§22, §23).

Two rules shape everything here, and both are about not lying:

**Sessions are clipped to the day.** A PC left on from 22:00 to 02:00 contributes two
hours to each date, not four to one of them. The stored `duration_seconds` is the length
of the session; a day view needs the length of its overlap with that day, which is a
different number and the one people actually check against a timesheet.

**Nothing sums across activity types.** ACTIVE, IDLE, APPLICATION and WEBSITE sessions
run in parallel and routinely cover the same wall-clock minute (§18). Adding "active
time" to "application time" would produce a number that means nothing, so every total
here is within a single type.

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

    return {
        "pc_on_seconds": total(ActivityType.PC_ON),
        "active_seconds": total(ActivityType.ACTIVE),
        "idle_seconds": total(ActivityType.IDLE),
        "top_applications": top_applications,
        "other_application_seconds": other_application_seconds,
        "top_websites": top_websites,
        "other_website_seconds": other_website_seconds,
        "session_count": len(sessions),
    }


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


def sessions_for_day(employee, day: dt.date, settings_obj=None):
    """Every session overlapping one office-local day, open ones included.

    The filter is an overlap test, not a start-time test: a session that began before
    midnight is part of this day too, and dropping it would lose the first hours of an
    early shift.
    """
    window_start, window_end = day_window(day, settings_obj)
    return list(
        Activity.objects.filter(employee=employee)
        .filter(start_time__lt=window_end)
        # Open sessions have no end and therefore always qualify.
        .filter(Q(end_time__gte=window_start) | Q(end_time__isnull=True))
        .select_related("computer")
        .order_by("start_time", "id")
    )


def activity_day(employee, day: dt.date, settings_obj=None, now=None) -> dict:
    """Everything §22 needs for one employee on one day."""
    settings_obj = settings_obj or AppSettings.load()
    window_start, window_end = day_window(day, settings_obj)
    sessions = sessions_for_day(employee, day, settings_obj)

    summary = summarise(sessions, window_start, window_end, now)
    summary["timeline"] = build_timeline(sessions, window_start, window_end, now)
    summary["date"] = day
    return summary
