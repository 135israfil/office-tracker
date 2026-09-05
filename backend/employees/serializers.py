"""Employee, shift and leave serializers.

The policy toggles from AppSettings are enforced here rather than in the UI alone: a
disabled feature must be impossible through the API, not merely hidden in the client.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from accounts.models import Role
from attendance.models import AppSettings

from .models import Employee, EmployeeShift, LeaveAdjustment

User = get_user_model()

HALF_DAY_STEP = Decimal("0.5")
WHOLE_DAY_STEP = Decimal("1.0")


def validate_leave_step(value, field_name="value"):
    """Leave amounts must land on a permitted increment (D6/A7)."""
    settings_obj = AppSettings.load()
    step = HALF_DAY_STEP if settings_obj.allow_half_day_leave else WHOLE_DAY_STEP
    if (Decimal(value) % step) != 0:
        unit = "0.5" if settings_obj.allow_half_day_leave else "whole"
        raise serializers.ValidationError(
            f"{field_name} must be in {unit} day increments (half-day leave is "
            f"{'enabled' if settings_obj.allow_half_day_leave else 'disabled'})."
        )
    return value


class EmployeeShiftSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeShift
        fields = ["id", "sequence", "start_time", "end_time"]

    def validate(self, attrs):
        start = attrs.get("start_time")
        end = attrs.get("end_time")
        if start and end and start >= end:
            raise serializers.ValidationError({"end_time": "Shift end must be after its start."})
        return attrs


class EmployeeSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email")
    is_user_active = serializers.BooleanField(source="user.is_active", read_only=True)
    shifts = EmployeeShiftSerializer(many=True, read_only=True)
    leave_remaining = serializers.DecimalField(max_digits=5, decimal_places=1, read_only=True)
    password = serializers.CharField(write_only=True, required=False, min_length=8)

    class Meta:
        model = Employee
        fields = [
            "id",
            "employee_id",
            "name",
            "email",
            "password",
            "phone",
            "department",
            "designation",
            "joining_date",
            "leave_total",
            "leave_used",
            "leave_remaining",
            "status",
            "is_user_active",
            "shifts",
            "created_at",
        ]
        read_only_fields = ["id", "created_at", "leave_used"]

    def validate_leave_total(self, value):
        return validate_leave_step(value, "leave_total")

    def validate_employee_id(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Employee ID cannot be blank.")
        return value

    def validate(self, attrs):
        user_data = attrs.get("user") or {}
        email = (user_data.get("email") or "").strip().lower()
        if email:
            existing = User.objects.filter(email__iexact=email)
            if self.instance:
                existing = existing.exclude(pk=self.instance.user_id)
            if existing.exists():
                raise serializers.ValidationError({"email": "That email is already in use."})
            attrs["user"]["email"] = email

        if not self.instance and not attrs.get("password"):
            raise serializers.ValidationError(
                {"password": "A password is required when creating an employee."}
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        user_data = validated_data.pop("user")
        password = validated_data.pop("password")

        user = User.objects.create_user(
            email=user_data["email"], password=password, role=Role.EMPLOYEE
        )
        employee = Employee.objects.create(user=user, **validated_data)

        # Seed a single default shift from AppSettings so every employee has a
        # schedule immediately; a split-shift employee gets a second row added later.
        settings_obj = AppSettings.load()
        EmployeeShift.objects.create(
            employee=employee,
            sequence=1,
            start_time=settings_obj.default_start_time,
            end_time=settings_obj.default_end_time,
        )
        return employee

    @transaction.atomic
    def update(self, instance, validated_data):
        user_data = validated_data.pop("user", None)
        password = validated_data.pop("password", None)

        if user_data and user_data.get("email"):
            instance.user.email = user_data["email"]
            instance.user.save(update_fields=["email"])
        if password:
            instance.user.set_password(password)
            instance.user.save(update_fields=["password"])

        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.full_clean(exclude=["user"])
        instance.save()
        return instance


class EmployeeShiftsWriteSerializer(serializers.Serializer):
    """Replaces an employee's whole shift set in one call.

    Whole-set replacement rather than per-row edits: shifts are only meaningful
    together, and partial updates make it easy to leave gaps or overlaps behind.
    """

    shifts = EmployeeShiftSerializer(many=True)

    def validate_shifts(self, value):
        if not value:
            raise serializers.ValidationError("An employee must have at least one shift.")

        settings_obj = AppSettings.load()
        if len(value) > 1 and not settings_obj.allow_split_shift:
            raise serializers.ValidationError(
                "Split shifts are disabled in settings. Enable them before adding a "
                "second shift."
            )
        if len(value) > 2:
            raise serializers.ValidationError("At most two shifts per employee are supported.")

        ordered = sorted(value, key=lambda shift: shift["start_time"])
        for earlier, later in zip(ordered, ordered[1:], strict=False):
            if earlier["end_time"] > later["start_time"]:
                raise serializers.ValidationError("Shifts must not overlap.")
        return ordered


class LeaveAdjustmentSerializer(serializers.ModelSerializer):
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)

    class Meta:
        model = LeaveAdjustment
        fields = [
            "id",
            "employee",
            "target",
            "delta",
            "reason",
            "created_by_email",
            "created_at",
        ]
        read_only_fields = ["id", "created_by_email", "created_at"]

    def validate_delta(self, value):
        if value == 0:
            raise serializers.ValidationError("Adjustment cannot be zero.")
        return validate_leave_step(value, "delta")

    def validate(self, attrs):
        employee = attrs["employee"]
        target = attrs.get("target", LeaveAdjustment.Target.TOTAL)
        delta = attrs["delta"]

        if target == LeaveAdjustment.Target.TOTAL:
            new_total = employee.leave_total + delta
            if new_total < 0:
                raise serializers.ValidationError(
                    {"delta": "That would put the total entitlement below zero."}
                )
            if new_total < employee.leave_used:
                raise serializers.ValidationError(
                    {"delta": "That would drop the total below the leave already used."}
                )
        else:
            new_used = employee.leave_used + delta
            if new_used < 0:
                raise serializers.ValidationError(
                    {"delta": "That would put leave used below zero."}
                )
            if new_used > employee.leave_total:
                raise serializers.ValidationError(
                    {"delta": "That would use more leave than the employee has."}
                )
        return attrs
