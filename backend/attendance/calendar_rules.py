"""Working-day and local-date rules.

Pure functions with no ORM access in the hot path, because these decide whether someone
is marked absent and are worth testing exhaustively. Everything that needs to know
"is this a working day?" or "which date does this instant belong to?" comes here rather
than reimplementing the rule locally.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo


def office_timezone(settings_obj) -> ZoneInfo:
    return ZoneInfo(settings_obj.timezone)


def local_date(instant: dt.datetime, settings_obj) -> dt.date:
    """Which office-local calendar date a UTC instant belongs to.

    This is the reason `TIME_ZONE` stays UTC and the office timezone is application
    data: an employee checking in at 23:30 UTC in a UTC+6 office is on *tomorrow's*
    date locally, and getting that wrong shifts whole days of attendance.
    """
    if instant.tzinfo is None:
        raise ValueError("local_date requires an aware datetime")
    return instant.astimezone(office_timezone(settings_obj)).date()


def is_weekend(day: dt.date, weekend_days) -> bool:
    return day.weekday() in set(weekend_days or [])


def is_working_day(day: dt.date, weekend_days, holiday_dates) -> bool:
    """A day is a working day unless it is a configured weekend day or a holiday.

    `weekend_days` comes from AppSettings (D4) and `holiday_dates` from the Holiday
    table, both passed in so callers can load them once and evaluate many dates.
    """
    if is_weekend(day, weekend_days):
        return False
    return day not in set(holiday_dates or ())


def working_days_between(start: dt.date, end: dt.date, weekend_days, holiday_dates):
    """Inclusive range of working days. Returns [] if end precedes start."""
    if end < start:
        return []
    weekend = set(weekend_days or [])
    holidays = set(holiday_dates or ())
    days = []
    current = start
    while current <= end:
        if current.weekday() not in weekend and current not in holidays:
            days.append(current)
        current += dt.timedelta(days=1)
    return days
