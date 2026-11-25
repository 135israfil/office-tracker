"""Serializers for the admin computer list and the agent endpoints.

The enrollment code is exposed to admins (they have to read it out to whoever installs
the agent) and never to anyone else. The device token appears in exactly one response
body, at registration, and is never stored in a form it can be recovered from.
"""

from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from employees.models import EmployeeStatus

from .models import Computer, ComputerStatus, LifecycleEvent


class ComputerSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.name", read_only=True)
    employee_code = serializers.CharField(source="employee.employee_id", read_only=True)
    is_registered = serializers.BooleanField(read_only=True)
    enrollment_code = serializers.CharField(source="formatted_enrollment_code", read_only=True)
    enrollment_valid = serializers.BooleanField(read_only=True)

    class Meta:
        model = Computer
        # Explicit rather than relying on ModelSerializer auto-detecting the model's
        # `unique_computer_name_per_employee` UniqueConstraint: that detection is a
        # genuinely fragile area across DRF versions — absent entirely in some, and
        # buggy for conditional constraints in others — so leaving this row's
        # rejection to chance meant it was one dependency bump away from a raw
        # IntegrityError (a 500) reaching an admin instead of a clean 400.
        validators = [
            UniqueTogetherValidator(
                queryset=Computer.objects.all(),
                fields=["employee", "computer_name"],
                message="This employee already has a computer with that name.",
            )
        ]
        fields = [
            "id",
            "employee",
            "employee_name",
            "employee_code",
            "computer_name",
            "device_type",
            "operating_system",
            "agent_version",
            "status",
            "last_seen_at",
            "registered_at",
            "is_registered",
            "enrollment_code",
            "enrollment_expires_at",
            "enrollment_valid",
            "created_at",
        ]
        read_only_fields = [
            "status",
            "last_seen_at",
            "registered_at",
            "agent_version",
            "operating_system",
            # Admins only ever create PC rows through this serializer (the code-based
            # enroll flow); an Android row is always auto-provisioned by a phone's own
            # login (see computers.services.get_or_create_mobile_device), never through
            # here, so there is no legitimate caller that would ever set this.
            "device_type",
            "enrollment_expires_at",
            "created_at",
        ]

    def validate_employee(self, employee):
        # Enrolling a machine to someone who has left would attribute activity to an
        # account that can no longer log in to see it.
        if employee.status != EmployeeStatus.ACTIVE:
            raise serializers.ValidationError("Cannot enrol a computer for an inactive employee.")
        return employee

    def validate_computer_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("A computer name is required.")
        return value


class RegisterSerializer(serializers.Serializer):
    """Body of `POST /api/agent/register/` — the only unauthenticated agent endpoint."""

    enrollment_code = serializers.CharField(max_length=32)
    computer_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    operating_system = serializers.CharField(max_length=120, required=False, allow_blank=True)
    agent_version = serializers.CharField(max_length=32, required=False, allow_blank=True)


class MobileDeviceSerializer(serializers.Serializer):
    """Body shared by every `/api/agent/mobile/*` endpoint.

    No enrollment code: these endpoints are bearer-token authenticated (the user's own
    login), which is what makes this the one agent request shape with no unauthenticated
    member at all.
    """

    computer_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    operating_system = serializers.CharField(max_length=120, required=False, allow_blank=True)
    agent_version = serializers.CharField(max_length=32, required=False, allow_blank=True)


class HeartbeatSerializer(serializers.Serializer):
    """Body of `POST /api/agent/heartbeat/`.

    `state` is what the agent believes it is doing right now; `event` is an optional
    lifecycle transition delivered on the same request rather than through a separate
    endpoint, so a shutdown notice rides the channel that is already known to work.
    """

    state = serializers.ChoiceField(
        choices=[ComputerStatus.ONLINE, ComputerStatus.IDLE],
        required=False,
        default=ComputerStatus.ONLINE,
    )
    event = serializers.ChoiceField(
        choices=LifecycleEvent.choices, required=False, allow_null=True, allow_blank=True
    )
    agent_version = serializers.CharField(max_length=32, required=False, allow_blank=True)


class EnrolledComputerSerializer(serializers.ModelSerializer):
    """What the agent is told about itself after registering."""

    employee_name = serializers.CharField(source="employee.name", read_only=True)

    class Meta:
        model = Computer
        fields = ["id", "computer_name", "employee_name"]
