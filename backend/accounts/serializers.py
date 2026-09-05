from django.contrib.auth import authenticate
from rest_framework import serializers

from .models import User


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs):
        request = self.context.get("request")
        user = authenticate(
            request=request,
            username=attrs["email"].strip().lower(),
            password=attrs["password"],
        )
        # A single generic message for both "no such account" and "wrong password":
        # distinguishing them tells an attacker which emails are registered.
        if user is None:
            raise serializers.ValidationError({"detail": "Invalid email or password."})
        if not user.is_active:
            raise serializers.ValidationError({"detail": "This account is disabled."})
        attrs["user"] = user
        return attrs


class CurrentUserSerializer(serializers.ModelSerializer):
    employee = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "role", "is_active", "employee"]
        read_only_fields = fields

    def get_employee(self, obj):
        employee = getattr(obj, "employee", None)
        if employee is None:
            return None
        return {
            "id": employee.id,
            "employee_id": employee.employee_id,
            "name": employee.name,
            "department": employee.department,
            "designation": employee.designation,
            "status": employee.status,
            "leave_total": str(employee.leave_total),
            "leave_used": str(employee.leave_used),
            "leave_remaining": str(employee.leave_remaining),
        }
