"""Activity API (§22, §23, §24).

Every endpoint here is subject to §30's data isolation rule, and it is enforced the same
way throughout: the employee whose data is being read is resolved by
`resolve_employee()`, which ignores any id an employee supplies and refuses outright if
they ask for someone else's. A view that forgets a permission class still cannot leak,
because the queryset is filtered on the resolved employee and nothing else.
"""

from __future__ import annotations

import datetime as dt

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from attendance.attendance_serializers import AttendanceSerializer
from attendance.calendar_rules import local_date
from attendance.models import AppSettings, Attendance
from employees.models import Employee

from .models import Activity
from .queries import activity_day, day_window
from .serializers import ActivitySerializer


def parse_date(value, settings_obj) -> dt.date:
    """A date parameter, defaulting to today in office-local terms."""
    if not value:
        return local_date(timezone.now(), settings_obj)
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid date: {value}") from exc


def resolve_employee(request, employee_param):
    """Which employee's data this request may read.

    Admins may name anyone. Everyone else gets themselves, and asking for another id is
    a 403 rather than a silent redirect to their own data — quietly returning something
    else would hide the attempt from both the caller and whoever reads the logs.
    """
    own = getattr(request.user, "employee", None)

    if request.user.is_admin:
        if not employee_param:
            return None
        try:
            return Employee.objects.select_related("user").get(pk=employee_param)
        except (Employee.DoesNotExist, ValueError, TypeError) as exc:
            raise PermissionDenied("No such employee.") from exc

    if own is None:
        raise PermissionDenied("This account is not linked to an employee record.")
    if employee_param and str(employee_param) != str(own.pk):
        raise PermissionDenied("You may only view your own activity.")
    return own


class ActivityViewSet(viewsets.ReadOnlyModelViewSet):
    """Raw sessions (§18), filtered by employee, date and type."""

    serializer_class = ActivitySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        settings_obj = AppSettings.load()
        params = self.request.query_params
        employee = resolve_employee(self.request, params.get("employee"))

        queryset = Activity.objects.select_related("computer", "employee")
        if employee is not None:
            queryset = queryset.filter(employee=employee)
        elif not self.request.user.is_admin:  # pragma: no cover - resolve_employee raises first
            return Activity.objects.none()

        if params.get("date"):
            window_start, window_end = day_window(parse_date(params["date"], settings_obj))
            queryset = queryset.filter(start_time__lt=window_end, end_time__gte=window_start)
        if params.get("type"):
            queryset = queryset.filter(activity_type=params["type"].upper())
        if params.get("computer"):
            queryset = queryset.filter(computer_id=params["computer"])
        return queryset


class ActivitySummaryView(APIView):
    """The §22 activity page payload for one employee on one day."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        settings_obj = AppSettings.load()
        employee = resolve_employee(request, request.query_params.get("employee"))
        if employee is None:
            return Response(
                {"detail": "An employee is required."}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            day = parse_date(request.query_params.get("date"), settings_obj)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        attendance = (
            Attendance.objects.filter(employee=employee, date=day)
            .prefetch_related("punches")
            .first()
        )

        return Response(
            {
                "employee": {
                    "id": employee.pk,
                    "employee_id": employee.employee_id,
                    "name": employee.name,
                    "department": employee.department,
                },
                "date": day,
                # The office timezone travels with the payload so the page renders
                # 09:02 for a 09:02 check-in regardless of where the admin is sitting.
                # Timestamps are UTC; the *day* they belong to was already decided in
                # office-local terms, and the display has to agree with that.
                "timezone": settings_obj.timezone,
                "attendance": AttendanceSerializer(attendance).data if attendance else None,
                "activity": activity_day(employee, day, settings_obj),
            }
        )
