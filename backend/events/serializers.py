"""Event serialization.

Unlike the Password Vault, nothing here is encrypted, so there is no
separate "reveal" action or write-only secret field — the detail view's
own `retrieve` is the action that (conditionally) gets audit-logged, per
`views.py`.
"""

from __future__ import annotations

from rest_framework import serializers

from core.models import AuditLog
from employees.models import Employee

from .models import Event, EventGrant


class _EmployeeStubSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = ["id", "employee_id", "name"]


class EventGrantSerializer(serializers.ModelSerializer):
    grantee = _EmployeeStubSerializer(read_only=True)
    granted_by = _EmployeeStubSerializer(read_only=True)

    class Meta:
        model = EventGrant
        fields = ["id", "grantee", "granted_by", "granted_at"]
        read_only_fields = fields


class EventSerializer(serializers.ModelSerializer):
    owner = _EmployeeStubSerializer(read_only=True)
    grants = EventGrantSerializer(many=True, read_only=True)
    phase = serializers.ReadOnlyField()
    visible_to = serializers.SerializerMethodField()
    last_admin_view = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "id",
            "title",
            "description",
            "start",
            "end",
            "all_day",
            "location",
            "status",
            "phase",
            "owner",
            "grants",
            "visible_to",
            "last_admin_view",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "phase",
            "owner",
            "grants",
            "visible_to",
            "last_admin_view",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        start = attrs.get("start", getattr(self.instance, "start", None))
        end = attrs.get("end", getattr(self.instance, "end", None))
        if end is not None and start is not None and end < start:
            raise serializers.ValidationError({"end": "An event cannot end before it starts."})
        return attrs

    def get_visible_to(self, obj):
        names = [obj.owner.name] + [grant.grantee.name for grant in obj.grants.all()]
        return names + ["All admins"]

    def get_last_admin_view(self, obj):
        entry = (
            AuditLog.objects.filter(
                action=AuditLog.Action.EVENT_VIEWED_BY_ADMIN,
                target_type="Event",
                target_id=str(obj.pk),
            )
            .order_by("-created_at")
            .first()
        )
        if entry is None:
            return None
        return {"admin": entry.actor.email if entry.actor else None, "at": entry.created_at}
