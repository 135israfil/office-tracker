"""Agent-facing API (§28).

Register, heartbeat, sync and config. `/api/agent/activity/` from §28 is folded into
`sync/`: one code path for online and offline means the offline path is exercised on
every single request instead of only during an outage.

Throttling is scoped rather than inherited. The defaults are tuned for browsers: an
anonymous 60/min would let a NAT-shared office exhaust its budget during a rollout,
while an authenticated 2000/hour is far more than a heartbeat loop ever needs.
"""

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from activities.serializers import SyncRequestSerializer
from activities.services import ingest_sessions
from attendance.models import AppSettings
from core.audit import record
from core.models import AuditLog

from .authentication import DeviceTokenAuthentication
from .permissions import IsRegisteredDevice
from .serializers import EnrolledComputerSerializer, HeartbeatSerializer, RegisterSerializer
from .services import (
    RegistrationError,
    agent_config_payload,
    record_heartbeat,
    register_device,
)


class AgentRegisterView(APIView):
    """Exchange a one-time enrollment code for a device token.

    Unauthenticated by necessity — the agent has no credential yet. The enrollment code
    is the credential, which is why it is single-use, expiring and rate-limited.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent-register"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            computer, token = register_device(
                enrollment_code=data["enrollment_code"],
                computer_name=data.get("computer_name", ""),
                operating_system=data.get("operating_system", ""),
                agent_version=data.get("agent_version", ""),
            )
        except RegistrationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        record(
            None,
            AuditLog.Action.DEVICE_REGISTERED,
            target=computer,
            payload={
                "computer_name": computer.computer_name,
                "employee": computer.employee.employee_id,
                "operating_system": computer.operating_system,
                "agent_version": computer.agent_version,
            },
        )

        # The only time the token is ever readable. It is stored hashed, so a lost token
        # means a new enrollment code, not a lookup.
        return Response(
            {
                "device_token": token,
                "computer": EnrolledComputerSerializer(computer).data,
                "config": agent_config_payload(computer=computer),
            },
            status=status.HTTP_201_CREATED,
        )


class AgentHeartbeatView(APIView):
    """Liveness plus the current active/idle state, and optionally one lifecycle event."""

    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsRegisteredDevice]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent"

    def post(self, request):
        serializer = HeartbeatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        config = record_heartbeat(
            request.auth,
            state=data.get("state"),
            event=data.get("event") or None,
            agent_version=data.get("agent_version", ""),
        )
        return Response({"status": request.auth.status, "config": config})


class AgentSyncView(APIView):
    """Batch upload of closed activity sessions (§19).

    Idempotent by construction: ingestion upserts on `(computer, client_event_id)`, so
    an agent that never saw the response to a batch can send it again without producing
    a single duplicate row. That is what makes it safe for the agent to mark a session
    synced only after a 2xx.
    """

    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsRegisteredDevice]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent"

    def post(self, request):
        serializer = SyncRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = ingest_sessions(request.auth, serializer.validated_data["sessions"])
        result["config"] = agent_config_payload(computer=request.auth)
        return Response(result)


class AgentConfigView(APIView):
    """Server-driven agent settings (§35) plus the fleet kill switch."""

    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsRegisteredDevice]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent"

    def get(self, request):
        return Response(agent_config_payload(AppSettings.load(), computer=request.auth))
