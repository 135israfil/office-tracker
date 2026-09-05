"""Dashboard assembly (§20, §21, §24).

Cross-cutting by nature — a dashboard is attendance plus computers plus activity — so it
lives in `core` rather than picking one of the three apps to own it.

The employee roster (§21) is the query most likely to become a problem at scale: one row
per employee, each needing today's attendance, their PC's status and their active and
idle time. It is written as three bulk queries plus in-memory assembly rather than a
per-employee loop, because the loop version is 4×N queries and looks fine with the five
employees a developer has in their database.
"""

from __future__ import annotations

import datetime as dt

from django.db.models import Count, Q
from django.utils import timezone

from activities.models import ActivityType
from activities.queries import day_window, overlap_seconds
from attendance.calendar_rules import is_working_day, local_date
from attendance.models import AppSettings, Attendance, AttendanceStatus, Holiday
from computers.models import Computer, ComputerStatus
from employees.models import Employee, EmployeeStatus


def _today(settings_obj) -> dt.date:
    return local_date(timezone.now(), settings_obj)


def attendance_counts(day: dt.date, settings_obj=None) -> dict:
    """§20's "Today's Attendance" block.

    `not_recorded` is deliberately separate from `absent`. Absence is a *derived* fact
    the nightly job materialises (A4); at 10am someone with no row has simply not
    arrived yet, and showing them as absent would be wrong for most of the working day.
    """
    settings_obj = settings_obj or AppSettings.load()
    total = Employee.objects.filter(status=EmployeeStatus.ACTIVE).count()

    rows = (
        Attendance.objects.filter(date=day, employee__status=EmployeeStatus.ACTIVE)
        .values("status")
        .annotate(count=Count("id"))
    )
    by_status = {row["status"]: row["count"] for row in rows}
    recorded = sum(by_status.values())

    return {
        "employees": total,
        "present": by_status.get(AttendanceStatus.PRESENT, 0),
        "late": by_status.get(AttendanceStatus.LATE, 0),
        "absent": by_status.get(AttendanceStatus.ABSENT, 0),
        "leave": by_status.get(AttendanceStatus.LEAVE, 0),
        "not_recorded": max(0, total - recorded),
        "is_working_day": is_working_day(
            day,
            settings_obj.weekend_days,
            set(Holiday.objects.filter(date=day).values_list("date", flat=True)),
        ),
    }


def computer_counts() -> dict:
    """§20's "PC Status" block.

    §20 lists Online, Active, Idle and Offline. Here "online" means answering heartbeats
    at all, and it is the sum of active and idle — which is why the example's 39 online
    breaks down into 34 active and 5 idle rather than being a fourth independent number.
    """
    rows = Computer.objects.values("status").annotate(count=Count("id"))
    by_status = {row["status"]: row["count"] for row in rows}

    active = by_status.get(ComputerStatus.ONLINE, 0)
    idle = by_status.get(ComputerStatus.IDLE, 0)
    return {
        "total": sum(by_status.values()),
        "online": active + idle,
        "active": active,
        "idle": idle,
        "offline": by_status.get(ComputerStatus.OFFLINE, 0),
        "disabled": by_status.get(ComputerStatus.DISABLED, 0),
        "unregistered": Computer.objects.filter(device_token_hash__isnull=True)
        .exclude(status=ComputerStatus.DISABLED)
        .count(),
    }


def admin_dashboard(day: dt.date | None = None, settings_obj=None) -> dict:
    settings_obj = settings_obj or AppSettings.load()
    day = day or _today(settings_obj)
    return {
        "date": day,
        "attendance": attendance_counts(day, settings_obj),
        "computers": computer_counts(),
    }


def employee_roster(day: dt.date | None = None, employees=None, settings_obj=None) -> list[dict]:
    """§21's employee list: one row per employee, with today's facts attached.

    Three queries regardless of headcount — employees, their attendance, their activity —
    then assembled in memory. Activity is clipped to the day by the same rule the
    activity page uses, so the two screens can never disagree.
    """
    settings_obj = settings_obj or AppSettings.load()
    day = day or _today(settings_obj)
    window_start, window_end = day_window(day, settings_obj)
    now = timezone.now()

    if employees is None:
        employees = Employee.objects.filter(status=EmployeeStatus.ACTIVE)
    employees = list(employees.select_related("user").order_by("name", "id"))
    employee_ids = [employee.pk for employee in employees]

    attendance_by_employee = {
        row.employee_id: row
        for row in Attendance.objects.filter(employee_id__in=employee_ids, date=day)
    }

    computers_by_employee: dict[int, list] = {}
    for computer in Computer.objects.filter(employee_id__in=employee_ids):
        computers_by_employee.setdefault(computer.employee_id, []).append(computer)

    # One query for the whole roster's activity rather than one per employee.
    from activities.models import Activity

    sessions_by_employee: dict[int, list] = {}
    session_rows = Activity.objects.filter(
        employee_id__in=employee_ids,
        activity_type__in=[ActivityType.ACTIVE, ActivityType.IDLE],
        start_time__lt=window_end,
    ).filter(Q(end_time__gte=window_start) | Q(end_time__isnull=True))
    for session in session_rows:
        sessions_by_employee.setdefault(session.employee_id, []).append(session)

    rows = []
    for employee in employees:
        attendance = attendance_by_employee.get(employee.pk)
        sessions = sessions_by_employee.get(employee.pk, [])
        computers = computers_by_employee.get(employee.pk, [])

        rows.append(
            {
                "employee_id": employee.pk,
                "employee_code": employee.employee_id,
                "name": employee.name,
                "department": employee.department,
                "attendance_status": attendance.status if attendance else None,
                "first_check_in_at": attendance.first_check_in_at if attendance else None,
                "last_check_out_at": attendance.last_check_out_at if attendance else None,
                "late_minutes": attendance.late_minutes if attendance else 0,
                # The best status among their machines: someone with a desktop and a
                # laptop is "online" if either is answering.
                "pc_status": _best_status(computers),
                "computer_count": len(computers),
                "active_seconds": sum(
                    overlap_seconds(s, window_start, window_end, now)
                    for s in sessions
                    if s.activity_type == ActivityType.ACTIVE
                ),
                "idle_seconds": sum(
                    overlap_seconds(s, window_start, window_end, now)
                    for s in sessions
                    if s.activity_type == ActivityType.IDLE
                ),
            }
        )
    return rows


# Best-first, so a person with two machines is reported by the liveliest one.
_STATUS_RANK = [
    ComputerStatus.ONLINE,
    ComputerStatus.IDLE,
    ComputerStatus.OFFLINE,
    ComputerStatus.DISABLED,
]


def _best_status(computers) -> str | None:
    if not computers:
        return None
    statuses = {computer.status for computer in computers}
    for status in _STATUS_RANK:
        if status in statuses:
            return status
    return None
