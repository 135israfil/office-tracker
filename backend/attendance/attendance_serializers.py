"""Attendance read/write serializers, kept separate from the settings serializers."""

from rest_framework import serializers

from .models import Attendance, AttendancePunch


class PunchSerializer(serializers.ModelSerializer):
    duration_seconds = serializers.IntegerField(read_only=True)

    class Meta:
        model = AttendancePunch
        fields = [
            "id",
            "sequence",
            "check_in_at",
            "check_in_latitude",
            "check_in_longitude",
            "check_in_accuracy_m",
            "check_in_distance_m",
            "check_in_location_status",
            "check_out_at",
            "check_out_latitude",
            "check_out_longitude",
            "check_out_accuracy_m",
            "check_out_distance_m",
            "check_out_location_status",
            "matched_shift",
            "scheduled_start",
            "late_minutes",
            "duration_seconds",
        ]
        read_only_fields = fields


class AttendanceSerializer(serializers.ModelSerializer):
    punches = PunchSerializer(many=True, read_only=True)
    employee_name = serializers.CharField(source="employee.name", read_only=True)
    employee_code = serializers.CharField(source="employee.employee_id", read_only=True)
    department = serializers.CharField(source="employee.department", read_only=True)

    class Meta:
        model = Attendance
        fields = [
            "id",
            "employee",
            "employee_name",
            "employee_code",
            "department",
            "date",
            "first_check_in_at",
            "last_check_out_at",
            "worked_seconds",
            "late_minutes",
            "status",
            "leave_fraction",
            "needs_review",
            "is_manually_adjusted",
            "adjustment_note",
            "punches",
        ]
        read_only_fields = fields


class PunchLocationSerializer(serializers.Serializer):
    """Payload sent by the browser on check-in and check-out."""

    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    accuracy_m = serializers.FloatField(required=False, allow_null=True)


class PunchCorrectionSerializer(serializers.Serializer):
    check_in_at = serializers.DateTimeField(required=False)
    check_out_at = serializers.DateTimeField(required=False, allow_null=True)
    note = serializers.CharField(max_length=300, required=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs.get("check_in_at") and "check_out_at" not in attrs:
            raise serializers.ValidationError("Provide check_in_at and/or check_out_at.")
        return attrs


class LeaveMarkSerializer(serializers.Serializer):
    employee = serializers.IntegerField()
    date = serializers.DateField()
    fraction = serializers.DecimalField(max_digits=2, decimal_places=1)
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True)
