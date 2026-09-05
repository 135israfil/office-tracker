"""Attendance operations (§6–§10).

All writes go through here rather than through serializers, so the check-in rules,
shift matching and day recomputation have exactly one implementation shared by the API,
the admin correction path and the nightly jobs.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .calendar_rules import local_date
from .geo import distance_from_office, location_status, validate_coordinates
from .models import (
    AppSettings,
    Attendance,
    AttendancePunch,
    AttendanceStatus,
    Holiday,
)
from .shift_matching import late_minutes_for, match_punch_to_shift, summarise_day

# A hard ceiling on punches per day. Not a business rule so much as a guard: without it
# a stuck client could create rows indefinitely.
MAX_PUNCHES_PER_DAY = 10


class AttendanceError(Exception):
    """Raised for rule violations that should surface as a 400, not a 500."""


def _office_time(instant, settings_obj) -> dt.time:
    from .calendar_rules import office_timezone

    return instant.astimezone(office_timezone(settings_obj)).time()


def recompute(attendance: Attendance, *, save=True) -> Attendance:
    """Recalculate the day-level summary from its punches.

    Called after every punch change, including admin corrections, so the denormalised
    columns can never drift from the punches they summarise.
    """
    # Query the punches explicitly rather than via `attendance.punches.all()`. If the
    # caller loaded this row with prefetch_related("punches") — as the admin list view
    # does — the related manager would hand back a cached list captured *before* the
    # edit, and the recomputed summary would silently be based on stale rows.
    punches = list(AttendancePunch.objects.filter(attendance_id=attendance.pk))
    summary = summarise_day(punches)

    attendance.first_check_in_at = summary["first_check_in_at"]
    attendance.last_check_out_at = summary["last_check_out_at"]
    attendance.worked_seconds = summary["worked_seconds"]
    attendance.late_minutes = summary["late_minutes"]
    attendance.needs_review = summary["unmatched_punches"] > 0

    if attendance.leave_fraction >= Decimal("1.0"):
        attendance.status = AttendanceStatus.LEAVE
    elif punches:
        attendance.status = (
            AttendanceStatus.LATE if summary["late_minutes"] > 0 else AttendanceStatus.PRESENT
        )
    else:
        # No punches and not on full leave. Whether that means ABSENT depends on the
        # calendar, which the nightly job decides; leaving the existing status alone
        # here avoids flipping a row to ABSENT the moment its last punch is deleted.
        attendance.status = attendance.status or AttendanceStatus.PRESENT

    if save:
        attendance.save()
    return attendance


def _get_or_create_day(employee, day: dt.date) -> Attendance:
    attendance, _ = Attendance.objects.get_or_create(
        employee=employee,
        date=day,
        defaults={"status": AttendanceStatus.PRESENT},
    )
    return attendance


@transaction.atomic
def check_in(employee, *, latitude, longitude, accuracy_m=None, now=None) -> AttendancePunch:
    """Open a new punch for the employee's current office-local date (§6)."""
    settings_obj = AppSettings.load()
    now = now or timezone.now()

    if not employee.is_active:
        raise AttendanceError("This employee is not active.")

    try:
        latitude, longitude = validate_coordinates(latitude, longitude)
    except ValueError as exc:
        raise AttendanceError(str(exc)) from exc

    day = local_date(now, settings_obj)
    attendance = _get_or_create_day(employee, day)

    # Lock the day so two rapid taps cannot both pass the open-punch check.
    attendance = Attendance.objects.select_for_update().get(pk=attendance.pk)

    if attendance.punches.filter(check_out_at__isnull=True).exists():
        raise AttendanceError("You are already checked in. Check out before checking in again.")

    existing = list(attendance.punches.all())
    if len(existing) >= MAX_PUNCHES_PER_DAY:
        raise AttendanceError(f"Maximum of {MAX_PUNCHES_PER_DAY} check-ins per day reached.")

    punch_time = _office_time(now, settings_obj)
    shifts = list(employee.shifts.all())
    matched_ids = [p.matched_shift_id for p in existing if p.matched_shift_id]
    shift = match_punch_to_shift(punch_time, shifts, matched_ids)

    # An unmatched punch is stored, not rejected: an employee who steps out twice should
    # still have their afternoon recorded. It carries no schedule, so no late minutes,
    # and it flags the day for admin review rather than the system guessing.
    scheduled_start = shift.start_time if shift else None

    distance = distance_from_office(latitude, longitude, settings_obj)
    status = location_status(distance, settings_obj.radius_meters)

    # §5 / D2. Refused before anything is written, so a blocked attempt leaves no
    # half-open punch behind. The message names the distance and the radius, because
    # "you are not at the office" is useless to someone standing in the lobby with a
    # bad GPS fix — they need to know whether to move or to call an admin.
    if status == "OUTSIDE" and settings_obj.require_check_in_inside_radius:
        raise AttendanceError(
            f"Check-in is only allowed inside the office radius. You are "
            f"{round(distance)} m away and the limit is {settings_obj.radius_meters} m."
        )

    punch = AttendancePunch.objects.create(
        attendance=attendance,
        sequence=len(existing) + 1,
        check_in_at=now,
        check_in_latitude=latitude,
        check_in_longitude=longitude,
        check_in_accuracy_m=accuracy_m,
        check_in_distance_m=round(distance, 1),
        check_in_location_status=status,
        matched_shift=shift,
        scheduled_start=scheduled_start,
        late_minutes=late_minutes_for(punch_time, scheduled_start),
    )

    recompute(attendance)
    # Rebind the cached relation: `punch.attendance` would otherwise be whatever
    # instance was attached at creation, and a caller serialising it would send the
    # pre-recompute summary. Cheap to do, and easy to miss.
    punch.attendance = attendance
    return punch


@transaction.atomic
def check_out(employee, *, latitude, longitude, accuracy_m=None, now=None) -> AttendancePunch:
    """Close the open punch (§7)."""
    settings_obj = AppSettings.load()
    now = now or timezone.now()

    try:
        latitude, longitude = validate_coordinates(latitude, longitude)
    except ValueError as exc:
        raise AttendanceError(str(exc)) from exc

    # Look for the open punch on today *or* yesterday: someone who checks in at 23:50
    # and out at 00:10 must be able to close the punch they actually opened.
    day = local_date(now, settings_obj)
    candidates = Attendance.objects.filter(
        employee=employee, date__in=[day, day - dt.timedelta(days=1)]
    ).order_by("-date")

    punch = None
    attendance = None
    for candidate in candidates:
        open_punch = (
            candidate.punches.filter(check_out_at__isnull=True).order_by("-sequence").first()
        )
        if open_punch:
            attendance = Attendance.objects.select_for_update().get(pk=candidate.pk)
            punch = open_punch
            break

    if punch is None:
        raise AttendanceError("You are not checked in.")

    if now < punch.check_in_at:
        raise AttendanceError("Check-out cannot be earlier than check-in.")

    distance = distance_from_office(latitude, longitude, settings_obj)
    punch.check_out_at = now
    punch.check_out_latitude = latitude
    punch.check_out_longitude = longitude
    punch.check_out_accuracy_m = accuracy_m
    punch.check_out_distance_m = round(distance, 1)
    punch.check_out_location_status = location_status(distance, settings_obj.radius_meters)
    punch.save()

    recompute(attendance)
    punch.attendance = attendance
    return punch


@transaction.atomic
def set_leave(employee, day: dt.date, fraction: Decimal, *, actor=None, reason="") -> Attendance:
    """Mark a day as leave (§10, D6).

    Consumes the balance through a LeaveAdjustment so the leave trail has one shape,
    rather than a parallel mechanism that reports would have to merge later.
    """
    from employees.models import Employee, LeaveAdjustment

    settings_obj = AppSettings.load()
    fraction = Decimal(str(fraction))

    if fraction not in (Decimal("0.0"), Decimal("0.5"), Decimal("1.0")):
        raise AttendanceError("Leave fraction must be 0, 0.5 or 1.")
    if fraction == Decimal("0.5") and not settings_obj.allow_half_day_leave:
        raise AttendanceError("Half-day leave is disabled in settings.")

    attendance = _get_or_create_day(employee, day)
    previous = attendance.leave_fraction
    delta = fraction - previous
    if delta == 0:
        return attendance

    locked = Employee.objects.select_for_update().get(pk=employee.pk)
    new_used = locked.leave_used + delta
    if new_used < 0:
        raise AttendanceError("That would put leave used below zero.")
    if new_used > locked.leave_total:
        raise AttendanceError("The employee does not have enough leave remaining.")

    locked.leave_used = new_used
    locked.save(update_fields=["leave_used", "updated_at"])

    LeaveAdjustment.objects.create(
        employee=locked,
        target=LeaveAdjustment.Target.USED,
        delta=delta,
        reason=reason or f"Leave marked for {day}",
        created_by=actor,
    )

    attendance.leave_fraction = fraction
    recompute(attendance)
    return attendance


def mark_absentees(day: dt.date, *, dry_run=False):
    """Create ABSENT rows for a past working day (§9, A4).

    Only runs for working days, per the configured weekend (D4) and the holiday
    calendar. Never touches a day that already has a row, so it cannot overwrite a real
    check-in or a leave marking.
    """
    from employees.models import Employee, EmployeeStatus

    from .calendar_rules import is_working_day

    settings_obj = AppSettings.load()
    holidays = set(Holiday.objects.values_list("date", flat=True))

    if not is_working_day(day, settings_obj.weekend_days, holidays):
        return {"date": day, "skipped": "not a working day", "created": 0}

    existing = set(Attendance.objects.filter(date=day).values_list("employee_id", flat=True))
    candidates = Employee.objects.filter(status=EmployeeStatus.ACTIVE).exclude(id__in=existing)
    # Someone who had not joined yet cannot be absent.
    candidates = candidates.filter(joining_date__lte=day) | candidates.filter(
        joining_date__isnull=True
    )

    to_create = [
        Attendance(employee=employee, date=day, status=AttendanceStatus.ABSENT)
        for employee in candidates.distinct()
    ]
    if not dry_run and to_create:
        Attendance.objects.bulk_create(to_create, ignore_conflicts=True)

    return {"date": day, "skipped": None, "created": len(to_create)}
