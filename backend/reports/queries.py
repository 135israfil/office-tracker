"""Building the §25 report rows.

Both reports are generators. That is not a style choice: an export covering a year must
not assemble the whole result set in memory before the first byte reaches the client,
and a generator lets the CSV writer stream row by row.

The activity report reuses `activities.queries.overlap_seconds` and `day_window` rather
than reimplementing them. The rule that a session is clipped to the day it is being
reported for — a PC on from 22:00 to 02:00 gives two hours to each date, not four to one
of them — has exactly one implementation, so the report and the dashboards can never
disagree about how long a day was.
"""

from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from activities.models import Activity, ActivityType
from activities.queries import day_window, overlap_seconds
from attendance.models import Attendance

# Rows are fetched in chunks so an export's memory stays flat regardless of range. The
# activity report goes one office-local day at a time for the same reason: the number
# of queries then scales with the number of days requested, which the caller chose,
# rather than with headcount, which they did not.
CHUNK_SIZE = 500


# --- Attendance report (§25) ------------------------------------------------


def attendance_rows(filters):
    """One row per employee per day that has an attendance record.

    Worked time comes from `worked_seconds`, never from last-check-out minus
    first-check-in. With split shifts (D7) those are different numbers, and the
    subtraction version counts a two-hour lunch break as work.
    """
    employee_ids = list(filters.employees().values_list("pk", flat=True))
    if not employee_ids:
        return

    queryset = (
        Attendance.objects.filter(
            employee_id__in=employee_ids,
            date__gte=filters.date_from,
            date__lte=filters.date_to,
        )
        .select_related("employee")
        .prefetch_related("punches")
        .order_by("date", "employee__name", "employee_id")
    )
    if filters.status:
        queryset = queryset.filter(status=filters.status)

    for record in queryset.iterator(chunk_size=CHUNK_SIZE):
        punches = list(record.punches.all())
        first = punches[0] if punches else None

        yield {
            "employee_id": record.employee_id,
            "employee_code": record.employee.employee_id,
            "employee_name": record.employee.name,
            "department": record.employee.department,
            "date": record.date,
            "first_check_in_at": record.first_check_in_at,
            "last_check_out_at": record.last_check_out_at,
            "worked_seconds": record.worked_seconds,
            "late_minutes": record.late_minutes,
            "status": record.status,
            "leave_fraction": str(record.leave_fraction),
            # §25 asks for "Check-in location". It is the location of the punch that
            # started the day; later punches carry their own and are in the detail rows.
            "check_in_location": first.check_in_location_status if first else "",
            "check_in_distance_m": first.check_in_distance_m if first else None,
            "check_in_accuracy_m": first.check_in_accuracy_m if first else None,
            "punch_count": len(punches),
            "needs_review": record.needs_review,
            "is_manually_adjusted": record.is_manually_adjusted,
            "punches": [
                {
                    "sequence": punch.sequence,
                    "check_in_at": punch.check_in_at,
                    "check_out_at": punch.check_out_at,
                    "duration_seconds": punch.duration_seconds,
                    "late_minutes": punch.late_minutes,
                    "scheduled_start": punch.scheduled_start,
                    "check_in_location": punch.check_in_location_status,
                    "check_in_distance_m": punch.check_in_distance_m,
                    "check_out_location": punch.check_out_location_status,
                }
                for punch in punches
            ],
        }


# --- PC activity report (§25) -----------------------------------------------


class _Totals:
    """Running totals for one employee, over one day or over the whole range.

    There is no `pc_on` total here: see activities/queries.py's summarise() for why
    "PC on" is reported as active + idle rather than the raw PC_ON session span — a
    heartbeat confirms the machine was reachable, but a gap in the sampler's own
    ACTIVE/IDLE coverage has no business being counted as "on" just because something
    else briefly answered the door.
    """

    __slots__ = ("active", "idle", "applications", "websites", "sessions")

    def __init__(self):
        self.active = 0
        self.idle = 0
        self.applications: dict[str, int] = {}
        self.websites: dict[str, int] = {}
        self.sessions = 0

    def add(self, session, seconds):
        self.sessions += 1
        if session.activity_type == ActivityType.ACTIVE:
            self.active += seconds
        elif session.activity_type == ActivityType.IDLE:
            self.idle += seconds
        elif session.activity_type == ActivityType.APPLICATION:
            name = (session.application_name or "").strip()
            if name:
                self.applications[name] = self.applications.get(name, 0) + seconds
        elif session.activity_type == ActivityType.WEBSITE:
            domain = (session.website_domain or "").strip()
            if domain:
                self.websites[domain] = self.websites.get(domain, 0) + seconds

    def merge(self, other):
        self.active += other.active
        self.idle += other.idle
        self.sessions += other.sessions
        for name, seconds in other.applications.items():
            self.applications[name] = self.applications.get(name, 0) + seconds
        for domain, seconds in other.websites.items():
            self.websites[domain] = self.websites.get(domain, 0) + seconds

    @property
    def is_empty(self) -> bool:
        return self.sessions == 0


def _top(totals: dict[str, int]) -> dict:
    """The single busiest label, ties broken alphabetically so runs are reproducible."""
    if not totals:
        return {"name": "", "seconds": 0}
    name, seconds = sorted(totals.items(), key=lambda item: (-item[1], item[0]))[0]
    return {"name": name, "seconds": seconds}


def _row(employee, day, totals: _Totals) -> dict:
    return {
        "employee_id": employee.pk,
        "employee_code": employee.employee_id,
        "employee_name": employee.name,
        "department": employee.department,
        # None when the rows are grouped by employee: the row covers the whole range,
        # and putting one of its dates in the column would be a lie about the others.
        "date": day,
        "pc_on_seconds": totals.active + totals.idle,
        "active_seconds": totals.active,
        "idle_seconds": totals.idle,
        "top_application": _top(totals.applications),
        "top_website": _top(totals.websites),
        "application_count": len(totals.applications),
        "website_count": len(totals.websites),
        "session_count": totals.sessions,
    }


def _day_totals(employee_ids, day, settings_obj, now) -> dict:
    """Every employee's clipped totals for one office-local day, in one query."""
    window_start, window_end = day_window(day, settings_obj)
    sessions = (
        Activity.objects.filter(employee_id__in=employee_ids, start_time__lt=window_end)
        # An open session has no end and therefore always overlaps; a session that
        # started before midnight belongs to this day too, so the filter is an overlap
        # test rather than a test on start_time alone.
        .filter(Q(end_time__gte=window_start) | Q(end_time__isnull=True))
        .only(
            "employee_id",
            "activity_type",
            "application_name",
            "website_domain",
            "start_time",
            "end_time",
        )
        .iterator(chunk_size=CHUNK_SIZE)
    )

    totals: dict[int, _Totals] = {}
    for session in sessions:
        seconds = overlap_seconds(session, window_start, window_end, now)
        if seconds <= 0:
            continue
        totals.setdefault(session.employee_id, _Totals()).add(session, seconds)
    return totals


def activity_rows(filters, now=None):
    """The §25 PC activity report.

    Grouped by day (the default) the rows stream out a day at a time. Grouped by
    employee they cannot: a row is only complete once the last day has been read, so
    those are accumulated and emitted at the end — bounded by headcount, not by range.

    Only employees with recorded activity produce rows. A zero row for every employee on
    every weekend day would be noise, and "no row" already reads as "nothing recorded".
    """
    now = now or timezone.now()
    employees = list(filters.employees())
    if not employees:
        return
    employee_ids = [employee.pk for employee in employees]

    accumulated: dict[int, _Totals] = {}

    for day in filters.days:
        day_totals = _day_totals(employee_ids, day, filters.settings, now)

        if filters.group == "employee":
            for employee_id, totals in day_totals.items():
                accumulated.setdefault(employee_id, _Totals()).merge(totals)
            continue

        # Ordered by employee so the output is stable, and in the same order the roster
        # and the attendance report use.
        for employee in employees:
            totals = day_totals.get(employee.pk)
            if totals is None or totals.is_empty:
                continue
            yield _row(employee, day, totals)

    if filters.group == "employee":
        for employee in employees:
            totals = accumulated.get(employee.pk)
            if totals is None or totals.is_empty:
                continue
            yield _row(employee, None, totals)


# --- Pagination over a generator --------------------------------------------


def page(rows, limit, offset):
    """One page of a generator, plus whether anything follows it.

    Reading one row past the page is how `has_more` is answered without a second full
    pass over the data — these reports have no cheap COUNT, because their rows are
    assembled in Python rather than selected by the database.
    """
    collected = []
    has_more = False
    for index, row in enumerate(rows):
        if index < offset:
            continue
        if len(collected) == limit:
            has_more = True
            break
        collected.append(row)
    return collected, has_more
