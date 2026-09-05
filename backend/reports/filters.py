"""Parsing and validating the §25 report filters.

Both reports take the same shape of filter — who, which department, which dates — so
the parsing lives here once rather than being re-implemented per view. Everything is
validated up front and turned into concrete values; the query layer below never sees a
raw query string and never has to guess what an empty parameter meant.
"""

from __future__ import annotations

import datetime as dt

from django.utils import timezone

from attendance.calendar_rules import local_date
from attendance.models import AttendanceStatus
from employees.models import Employee, EmployeeStatus

# A report is bounded, and the bound is stated rather than discovered. Without it a
# typo'd year ("2026" vs "2016") asks the database for a decade of rows and the export
# either times out or quietly produces something nobody will read.
MAX_RANGE_DAYS = 366

# JSON page size. Exports ignore this entirely — an export that silently stopped at row
# 200 would be worse than no export at all.
DEFAULT_LIMIT = 200
MAX_LIMIT = 1000


class FilterError(ValueError):
    """A filter the caller got wrong. Views turn this into a 400."""


def _date(value, field):
    try:
        return dt.date.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise FilterError(f"Invalid {field}: {value}") from exc


def _int(value, field, *, minimum, maximum):
    try:
        number = int(value)
    except (ValueError, TypeError) as exc:
        raise FilterError(f"Invalid {field}: {value}") from exc
    return max(minimum, min(maximum, number))


class ReportFilters:
    """The resolved filters for one report request."""

    def __init__(self, params, settings_obj):
        self.settings = settings_obj
        today = local_date(timezone.now(), settings_obj)

        # `date` is shorthand for a one-day range. Supporting both spellings matters
        # because §25 lists "Date" and "Date range" as separate filters, and the two
        # produce identical results for a single day.
        single = params.get("date")
        date_from = params.get("date_from")
        date_to = params.get("date_to")

        if single:
            self.date_from = self.date_to = _date(single, "date")
        else:
            self.date_from = _date(date_from, "date_from") if date_from else today
            self.date_to = _date(date_to, "date_to") if date_to else self.date_from

        if self.date_to < self.date_from:
            raise FilterError("date_to cannot be earlier than date_from.")
        span = (self.date_to - self.date_from).days + 1
        if span > MAX_RANGE_DAYS:
            raise FilterError(f"Date range is {span} days; the maximum is {MAX_RANGE_DAYS}.")

        self.employee_id = params.get("employee") or None
        if self.employee_id is not None:
            self.employee_id = _int(self.employee_id, "employee", minimum=1, maximum=2**31 - 1)

        self.department = (params.get("department") or "").strip()
        self.search = (params.get("search") or "").strip()

        status = (params.get("status") or "").strip().upper()
        if status and status not in AttendanceStatus.values:
            raise FilterError(f"Unknown status: {status}")
        self.status = status

        group = (params.get("group") or "day").strip().lower()
        if group not in ("day", "employee"):
            raise FilterError("group must be 'day' or 'employee'.")
        self.group = group

        # Employees who left still have history, and a report that hid it would make
        # last quarter's numbers change every time somebody is offboarded.
        self.include_inactive = params.get("include_inactive") in ("1", "true", "True")

        self.limit = _int(params.get("limit", DEFAULT_LIMIT), "limit", minimum=1, maximum=MAX_LIMIT)
        self.offset = _int(params.get("offset", 0), "offset", minimum=0, maximum=10**9)

    @property
    def days(self):
        """Every office-local date in the range, in order."""
        day = self.date_from
        while day <= self.date_to:
            yield day
            day += dt.timedelta(days=1)

    @property
    def day_count(self) -> int:
        return (self.date_to - self.date_from).days + 1

    def employees(self):
        """The employees this report covers, ordered the way the rows will be."""
        queryset = Employee.objects.select_related("user")
        if not self.include_inactive:
            queryset = queryset.filter(status=EmployeeStatus.ACTIVE)
        if self.employee_id:
            queryset = queryset.filter(pk=self.employee_id)
        if self.department:
            queryset = queryset.filter(department__iexact=self.department)
        if self.search:
            queryset = queryset.filter(name__icontains=self.search)
        return queryset.order_by("name", "id")

    def describe(self) -> dict:
        """The filters echoed back, for the UI header and the audit trail."""
        return {
            "date_from": self.date_from.isoformat(),
            "date_to": self.date_to.isoformat(),
            "employee": self.employee_id,
            "department": self.department,
            "search": self.search,
            "status": self.status,
            "group": self.group,
            "include_inactive": self.include_inactive,
        }
