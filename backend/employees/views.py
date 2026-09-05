"""Employee management API (§4, §10, §30).

Every mutation writes an audit entry. Disabling an employee deactivates their login
rather than deleting the row, because attendance and activity history must survive the
person leaving.
"""

from django.db import transaction
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.audit import diff, record
from core.models import AuditLog
from core.permissions import IsAdmin

from .models import Employee, EmployeeShift, EmployeeStatus, LeaveAdjustment
from .serializers import (
    EmployeeSerializer,
    EmployeeShiftsWriteSerializer,
    LeaveAdjustmentSerializer,
)

AUDITED_FIELDS = [
    "employee_id",
    "name",
    "phone",
    "department",
    "designation",
    "joining_date",
    "leave_total",
    "status",
]


def snapshot(employee):
    data = {field: getattr(employee, field) for field in AUDITED_FIELDS}
    data["email"] = employee.user.email
    # JSON-safe: dates and Decimals do not serialise into a JSONField as-is.
    return {key: (str(value) if value is not None else None) for key, value in data.items()}


class EmployeeViewSet(viewsets.ModelViewSet):
    serializer_class = EmployeeSerializer
    permission_classes = [IsAdmin]
    # No DestroyModelMixin: employees are disabled, never deleted (§4).
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        queryset = Employee.objects.select_related("user").prefetch_related("shifts").all()
        params = self.request.query_params

        search = params.get("search")
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(employee_id__icontains=search)
                | Q(user__email__icontains=search)
            )
        department = params.get("department")
        if department:
            queryset = queryset.filter(department__iexact=department)
        employee_status = params.get("status")
        if employee_status:
            queryset = queryset.filter(status=employee_status.upper())
        return queryset

    def perform_create(self, serializer):
        employee = serializer.save()
        record(
            self.request.user,
            AuditLog.Action.EMPLOYEE_CREATED,
            target=employee,
            payload=snapshot(employee),
        )

    def perform_update(self, serializer):
        before = snapshot(serializer.instance)
        employee = serializer.save()
        changes = diff(before, snapshot(employee))
        if changes:
            record(
                self.request.user,
                AuditLog.Action.EMPLOYEE_UPDATED,
                target=employee,
                payload={"changes": changes},
            )

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def disable(self, request, pk=None):
        employee = self.get_object()
        if employee.status == EmployeeStatus.INACTIVE:
            return Response({"detail": "Employee is already disabled."}, status=400)

        employee.status = EmployeeStatus.INACTIVE
        employee.save(update_fields=["status", "updated_at"])
        # Disabling must also stop the login, otherwise an "inactive" employee can
        # still authenticate and check in.
        employee.user.is_active = False
        employee.user.save(update_fields=["is_active"])

        record(request.user, AuditLog.Action.EMPLOYEE_DISABLED, target=employee)
        return Response(self.get_serializer(employee).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def enable(self, request, pk=None):
        employee = self.get_object()
        if employee.status == EmployeeStatus.ACTIVE:
            return Response({"detail": "Employee is already active."}, status=400)

        employee.status = EmployeeStatus.ACTIVE
        employee.save(update_fields=["status", "updated_at"])
        employee.user.is_active = True
        employee.user.save(update_fields=["is_active"])

        record(request.user, AuditLog.Action.EMPLOYEE_ENABLED, target=employee)
        return Response(self.get_serializer(employee).data)

    @action(detail=True, methods=["get", "put"])
    def shifts(self, request, pk=None):
        employee = self.get_object()

        if request.method == "GET":
            return Response(EmployeeSerializer(employee).data["shifts"])

        serializer = EmployeeShiftsWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        shifts = serializer.validated_data["shifts"]

        before = [
            {"sequence": s.sequence, "start": str(s.start_time), "end": str(s.end_time)}
            for s in employee.shifts.all()
        ]

        with transaction.atomic():
            employee.shifts.all().delete()
            for index, shift in enumerate(shifts, start=1):
                EmployeeShift.objects.create(
                    employee=employee,
                    sequence=index,
                    start_time=shift["start_time"],
                    end_time=shift["end_time"],
                )

        after = [
            {"sequence": s.sequence, "start": str(s.start_time), "end": str(s.end_time)}
            for s in employee.shifts.all()
        ]
        record(
            request.user,
            AuditLog.Action.SHIFTS_UPDATED,
            target=employee,
            payload={"from": before, "to": after},
        )
        return Response(after, status=status.HTTP_200_OK)


class LeaveAdjustmentViewSet(viewsets.ModelViewSet):
    """Create-and-list only: adjustments are an append-only trail (§10)."""

    serializer_class = LeaveAdjustmentSerializer
    permission_classes = [IsAdmin]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = LeaveAdjustment.objects.select_related("employee", "created_by")
        employee_id = self.request.query_params.get("employee")
        if employee_id:
            queryset = queryset.filter(employee_id=employee_id)
        return queryset

    @transaction.atomic
    def perform_create(self, serializer):
        adjustment = serializer.save(created_by=self.request.user)

        # Apply the delta to the balance the adjustment targets. select_for_update
        # prevents two concurrent adjustments from both reading the same starting
        # balance and one silently overwriting the other.
        employee = Employee.objects.select_for_update().get(pk=adjustment.employee_id)
        if adjustment.target == LeaveAdjustment.Target.TOTAL:
            employee.leave_total += adjustment.delta
            employee.save(update_fields=["leave_total", "updated_at"])
        else:
            employee.leave_used += adjustment.delta
            employee.save(update_fields=["leave_used", "updated_at"])

        record(
            self.request.user,
            AuditLog.Action.LEAVE_ADJUSTED,
            target=employee,
            payload={
                "target": adjustment.target,
                "delta": str(adjustment.delta),
                "reason": adjustment.reason,
                "leave_total": str(employee.leave_total),
                "leave_used": str(employee.leave_used),
            },
        )
