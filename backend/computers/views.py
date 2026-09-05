"""Admin computer management (§12).

Computers are enrolled, disabled and re-enabled — never deleted. Their activity history
has to outlive the machine, exactly as employee records outlive the employee.
"""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.audit import record
from core.models import AuditLog
from core.permissions import IsAdmin

from .models import Computer, ComputerStatus
from .serializers import ComputerSerializer
from .services import close_session, sweep_offline_computers


class ComputerViewSet(viewsets.ModelViewSet):
    serializer_class = ComputerSerializer
    permission_classes = [IsAdmin]
    # No DELETE: activity history must survive the machine being retired.
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        queryset = Computer.objects.select_related("employee", "employee__user")
        params = self.request.query_params

        if params.get("employee"):
            queryset = queryset.filter(employee_id=params["employee"])
        if params.get("status"):
            queryset = queryset.filter(status=params["status"].upper())
        if params.get("search"):
            queryset = queryset.filter(computer_name__icontains=params["search"])
        return queryset

    def list(self, request, *args, **kwargs):
        # Sweep before answering. The cron job is the backstop; without this call a
        # dashboard would happily show a machine as online long after it stopped
        # answering, which is exactly the question this screen exists to answer.
        sweep_offline_computers()
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        computer = serializer.save()
        computer.issue_enrollment_code()
        computer.save(update_fields=["enrollment_code", "enrollment_expires_at", "updated_at"])
        record(
            self.request.user,
            AuditLog.Action.DEVICE_CREATED,
            target=computer,
            payload={
                "computer_name": computer.computer_name,
                "employee": computer.employee.employee_id,
                "expires_at": computer.enrollment_expires_at.isoformat(),
            },
        )

    @action(detail=True, methods=["post"], url_path="issue-code")
    def issue_code(self, request, pk=None):
        """Hand out a fresh enrollment code, e.g. after a machine is rebuilt.

        This does not revoke the current token: an agent that is still working keeps
        working until the new registration replaces it. Revoking is `disable`.
        """
        computer = self.get_object()
        if computer.is_disabled:
            return Response(
                {"detail": "Enable the computer before issuing a new code."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        computer.issue_enrollment_code()
        computer.save(update_fields=["enrollment_code", "enrollment_expires_at", "updated_at"])
        record(
            request.user,
            AuditLog.Action.DEVICE_CODE_ISSUED,
            target=computer,
            payload={"expires_at": computer.enrollment_expires_at.isoformat()},
        )
        return Response(self.get_serializer(computer).data)

    @action(detail=True, methods=["post"])
    def disable(self, request, pk=None):
        """Revoke the device credential and stop accepting its data (§29).

        The token hash is cleared, not just flagged: a disabled machine that is later
        re-enabled must go through enrolment again rather than silently resuming with a
        credential that may be exactly why it was disabled.
        """
        computer = self.get_object()
        if computer.is_disabled:
            return Response({"detail": "Computer is already disabled."}, status=400)

        close_session(computer, computer.last_seen_at or computer.updated_at, by_server=True)
        computer.status = ComputerStatus.DISABLED
        computer.device_token_hash = None
        computer.enrollment_code = None
        computer.enrollment_expires_at = None
        computer.save()

        record(request.user, AuditLog.Action.DEVICE_DISABLED, target=computer)
        return Response(self.get_serializer(computer).data)

    @action(detail=True, methods=["post"])
    def enable(self, request, pk=None):
        computer = self.get_object()
        if not computer.is_disabled:
            return Response({"detail": "Computer is not disabled."}, status=400)

        computer.status = ComputerStatus.OFFLINE
        # Clear the credential unconditionally rather than trusting that `disable` was
        # the only way this row reached DISABLED — someone may have flipped it in the
        # Django admin. Re-enabling always means re-enrolling.
        computer.device_token_hash = None
        code = computer.issue_enrollment_code()
        computer.save()

        record(
            request.user,
            AuditLog.Action.DEVICE_ENABLED,
            target=computer,
            payload={
                "code_reissued": True,
                "expires_at": computer.enrollment_expires_at.isoformat(),
            },
        )
        data = self.get_serializer(computer).data
        data["enrollment_code"] = code
        return Response(data)
