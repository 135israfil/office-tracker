from django.db import connection
from django.utils import timezone
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from activities.queries import activity_day
from activities.views import parse_date
from attendance.attendance_serializers import AttendanceSerializer
from attendance.calendar_rules import local_date
from attendance.models import AppSettings, Attendance
from computers.models import Computer, ComputerStatus
from employees.models import Employee, EmployeeStatus

from .dashboards import admin_dashboard, employee_roster
from .permissions import IsAdmin


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health(request):
    """Liveness + database reachability, for Docker healthchecks and uptime probes."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return Response({"status": "error", "database": "unreachable"}, status=503)
    return Response({"status": "ok", "database": "ok"})


class AdminDashboardView(APIView):
    """§20: today's attendance counts and PC status counts."""

    permission_classes = [IsAdmin]

    def get(self, request):
        settings_obj = AppSettings.load()
        try:
            day = parse_date(request.query_params.get("date"), settings_obj)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        # Stale computer rows would make the PC panel claim machines are online long
        # after they stopped answering, which is the one thing this panel exists to say.
        from computers.services import sweep_offline_computers

        sweep_offline_computers(settings_obj=settings_obj)
        return Response({**admin_dashboard(day, settings_obj), "timezone": settings_obj.timezone})


class EmployeeRosterView(APIView):
    """§21: the employee list with today's attendance, PC status and activity."""

    permission_classes = [IsAdmin]

    def get(self, request):
        settings_obj = AppSettings.load()
        try:
            day = parse_date(request.query_params.get("date"), settings_obj)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        employees = Employee.objects.filter(status=EmployeeStatus.ACTIVE)
        if request.query_params.get("department"):
            employees = employees.filter(department__iexact=request.query_params["department"])
        if request.query_params.get("search"):
            employees = employees.filter(name__icontains=request.query_params["search"])

        return Response(
            {
                "date": day,
                "timezone": settings_obj.timezone,
                "employees": employee_roster(day, employees, settings_obj),
            }
        )


class MySummaryView(APIView):
    """§24: the employee's own dashboard. Strictly own-data.

    There is no employee parameter at all — not one that is validated, one that does not
    exist. The employee comes from `request.user`, so there is nothing to tamper with.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        employee = getattr(request.user, "employee", None)
        if employee is None:
            return Response(
                {"detail": "This account is not linked to an employee record."}, status=400
            )

        settings_obj = AppSettings.load()
        try:
            day = parse_date(request.query_params.get("date"), settings_obj)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        today = local_date(timezone.now(), settings_obj)
        attendance = (
            Attendance.objects.filter(employee=employee, date=day)
            .prefetch_related("punches")
            .first()
        )
        computers = list(Computer.objects.filter(employee=employee))

        return Response(
            {
                "date": day,
                "timezone": settings_obj.timezone,
                "is_today": day == today,
                "employee": {
                    "id": employee.pk,
                    "employee_id": employee.employee_id,
                    "name": employee.name,
                    "department": employee.department,
                    "designation": employee.designation,
                },
                "attendance": AttendanceSerializer(attendance).data if attendance else None,
                "leave": {
                    "total": str(employee.leave_total),
                    "used": str(employee.leave_used),
                    "remaining": str(employee.leave_remaining),
                },
                "activity": activity_day(employee, day, settings_obj),
                "computers": [
                    {
                        "id": computer.pk,
                        "computer_name": computer.computer_name,
                        "status": computer.status,
                        "last_seen_at": computer.last_seen_at,
                    }
                    for computer in computers
                    if computer.status != ComputerStatus.DISABLED
                ],
            }
        )
