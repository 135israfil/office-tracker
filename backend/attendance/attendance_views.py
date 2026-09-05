"""Attendance API (§6–§10).

Employee endpoints resolve the employee from `request.user` and never from a parameter,
so there is no id an employee could substitute to reach someone else's record.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.audit import record
from core.models import AuditLog
from core.permissions import IsAdmin

from .attendance_serializers import (
    AttendanceSerializer,
    LeaveMarkSerializer,
    PunchCorrectionSerializer,
    PunchLocationSerializer,
)
from .calendar_rules import local_date
from .models import AppSettings, Attendance, AttendancePunch
from .services import AttendanceError, check_in, check_out, recompute, set_leave


def _employee_or_error(request):
    employee = getattr(request.user, "employee", None)
    if employee is None:
        return None, Response(
            {"detail": "This account is not linked to an employee record."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return employee, None


class CheckInView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        employee, error = _employee_or_error(request)
        if error:
            return error

        serializer = PunchLocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            punch = check_in(employee, **serializer.validated_data)
        except AttendanceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(AttendanceSerializer(punch.attendance).data, status=status.HTTP_201_CREATED)


class CheckOutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        employee, error = _employee_or_error(request)
        if error:
            return error

        serializer = PunchLocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            punch = check_out(employee, **serializer.validated_data)
        except AttendanceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(AttendanceSerializer(punch.attendance).data)


class MyAttendanceView(APIView):
    """Own history only (§30 employee data isolation)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        employee, error = _employee_or_error(request)
        if error:
            return error

        queryset = (
            Attendance.objects.filter(employee=employee)
            .select_related("employee")
            .prefetch_related("punches")
        )
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)

        return Response(AttendanceSerializer(queryset[:200], many=True).data)


class MyTodayView(APIView):
    """Drives the check-in page: what button should the employee see right now?"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        employee, error = _employee_or_error(request)
        if error:
            return error

        settings_obj = AppSettings.load()
        today = local_date(timezone.now(), settings_obj)
        attendance = (
            Attendance.objects.filter(employee=employee, date=today)
            .prefetch_related("punches")
            .first()
        )

        open_punch = attendance.open_punch if attendance else None
        return Response(
            {
                "date": today,
                "checked_in": open_punch is not None,
                "open_since": open_punch.check_in_at if open_punch else None,
                "attendance": AttendanceSerializer(attendance).data if attendance else None,
                "office": {
                    "name": settings_obj.office_name,
                    "latitude": str(settings_obj.latitude),
                    "longitude": str(settings_obj.longitude),
                    "radius_meters": settings_obj.radius_meters,
                },
                "shifts": [
                    {"sequence": s.sequence, "start_time": s.start_time, "end_time": s.end_time}
                    for s in employee.shifts.all()
                ],
                "leave": {
                    "total": str(employee.leave_total),
                    "used": str(employee.leave_used),
                    "remaining": str(employee.leave_remaining),
                },
            }
        )


class AttendanceViewSet(viewsets.ReadOnlyModelViewSet):
    """Admin view of everyone's attendance, plus correction actions (§9)."""

    serializer_class = AttendanceSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        queryset = Attendance.objects.select_related("employee").prefetch_related("punches")
        params = self.request.query_params

        if params.get("employee"):
            queryset = queryset.filter(employee_id=params["employee"])
        if params.get("department"):
            queryset = queryset.filter(employee__department__iexact=params["department"])
        if params.get("date"):
            queryset = queryset.filter(date=params["date"])
        if params.get("date_from"):
            queryset = queryset.filter(date__gte=params["date_from"])
        if params.get("date_to"):
            queryset = queryset.filter(date__lte=params["date_to"])
        if params.get("status"):
            queryset = queryset.filter(status=params["status"].upper())
        if params.get("needs_review") in ("1", "true", "True"):
            queryset = queryset.filter(needs_review=True)
        if params.get("location") in ("INSIDE", "OUTSIDE"):
            queryset = queryset.filter(punches__check_in_location_status=params["location"])
        return queryset.distinct()

    @action(detail=True, methods=["patch"], url_path="punches/(?P<punch_id>[^/.]+)")
    @transaction.atomic
    def correct_punch(self, request, pk=None, punch_id=None):
        attendance = self.get_object()
        try:
            punch = attendance.punches.get(pk=punch_id)
        except AttendancePunch.DoesNotExist:
            return Response({"detail": "No such punch on this day."}, status=404)

        serializer = PunchCorrectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        before = {
            "check_in_at": punch.check_in_at.isoformat(),
            "check_out_at": punch.check_out_at.isoformat() if punch.check_out_at else None,
        }

        if data.get("check_in_at"):
            punch.check_in_at = data["check_in_at"]
        if "check_out_at" in data:
            punch.check_out_at = data["check_out_at"]

        if punch.check_out_at and punch.check_out_at < punch.check_in_at:
            return Response({"detail": "Check-out cannot be earlier than check-in."}, status=400)

        # Late minutes are recalculated against the snapshot taken at check-in, not
        # against the employee's current schedule, so a correction cannot retroactively
        # apply a schedule change that happened afterwards.
        from .shift_matching import late_minutes_for

        settings_obj = AppSettings.load()
        from .calendar_rules import office_timezone

        punch_time = punch.check_in_at.astimezone(office_timezone(settings_obj)).time()
        punch.late_minutes = late_minutes_for(punch_time, punch.scheduled_start)
        punch.save()

        attendance.is_manually_adjusted = True
        attendance.adjusted_by = request.user
        attendance.adjustment_note = data.get("note", "")
        recompute(attendance)

        record(
            request.user,
            AuditLog.Action.ATTENDANCE_CORRECTED,
            target=attendance,
            payload={
                "punch": punch.id,
                "from": before,
                "to": {
                    "check_in_at": punch.check_in_at.isoformat(),
                    "check_out_at": punch.check_out_at.isoformat() if punch.check_out_at else None,
                },
                "note": data.get("note", ""),
            },
        )
        return Response(self.get_serializer(attendance).data)


class MarkLeaveView(APIView):
    """Admin marks a day as full or half leave (§10, D6)."""

    permission_classes = [IsAdmin]

    def post(self, request):
        from employees.models import Employee

        serializer = LeaveMarkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            employee = Employee.objects.get(pk=data["employee"])
        except Employee.DoesNotExist:
            return Response({"detail": "No such employee."}, status=404)

        try:
            attendance = set_leave(
                employee,
                data["date"],
                data["fraction"],
                actor=request.user,
                reason=data.get("reason", ""),
            )
        except AttendanceError as exc:
            return Response({"detail": str(exc)}, status=400)

        record(
            request.user,
            AuditLog.Action.ATTENDANCE_CORRECTED,
            target=attendance,
            payload={
                "leave_fraction": str(attendance.leave_fraction),
                "date": str(data["date"]),
                "reason": data.get("reason", ""),
            },
        )
        return Response(AttendanceSerializer(attendance).data)
