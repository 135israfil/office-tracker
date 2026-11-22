"""Event serialization.

Unlike the Password Vault, nothing here is encrypted, so there is no
separate "reveal" action or write-only secret field — the detail view's
own `retrieve` is the action that (conditionally) gets audit-logged, per
`views.py`.

`budget`/`document_status`/`financial_status` are read-only here and absent
from the response entirely for a non-admin viewer (`to_representation`):
they are admin-only fields, written only through the dedicated `financials`
action in `views.py`, never through the ordinary owner-editable `update`.

`assigned_lead`/`booking_status` stay writable here too (the owner edits
them through the ordinary `update`), but an admin may *also* set them on an
event they do not own, through the dedicated `coordination` action.
"""

from __future__ import annotations

import nh3
from rest_framework import serializers

from core.models import AuditLog
from employees.models import Employee

from .models import Event

ADMIN_ONLY_FIELDS = ("budget", "document_status", "financial_status")


class _EmployeeStubSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = ["id", "employee_id", "name"]


class EventSerializer(serializers.ModelSerializer):
    owner = _EmployeeStubSerializer(read_only=True)
    last_admin_view = serializers.SerializerMethodField()
    assigned_lead = _EmployeeStubSerializer(read_only=True)
    assigned_lead_id = serializers.PrimaryKeyRelatedField(
        source="assigned_lead",
        queryset=Employee.objects.all(),
        allow_null=True,
        required=False,
        write_only=True,
    )

    class Meta:
        model = Event
        fields = [
            "id",
            "title",
            "agency_name",
            "venue_name",
            "setup",
            "assigned_lead",
            "assigned_lead_id",
            "booking_status",
            "alert_on",
            "budget",
            "document_status",
            "financial_status",
            "owner",
            "last_admin_view",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "owner",
            "last_admin_view",
            "created_at",
            "updated_at",
            *ADMIN_ONLY_FIELDS,
        ]

    def validate_setup(self, value):
        # `setup` is rich text from the frontend's editor, rendered back to
        # every viewer once an event is LOCKED — sanitized here, once, so no
        # renderer has to trust it, the same reasoning a stored-XSS field
        # always needs regardless of which client wrote it.
        return nh3.clean(value)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request is None or not request.user.is_admin:
            for field in ADMIN_ONLY_FIELDS:
                data.pop(field, None)
        return data

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


class EventFinancialsSerializer(serializers.ModelSerializer):
    """The admin-only slice of an event, written only through
    `EventViewSet.financials` — see the module docstring."""

    class Meta:
        model = Event
        fields = list(ADMIN_ONLY_FIELDS)


class EventCoordinationSerializer(serializers.ModelSerializer):
    """The admin-regardless-of-owner slice of an event, written only through
    `EventViewSet.coordination` — see the module docstring."""

    assigned_lead_id = serializers.PrimaryKeyRelatedField(
        source="assigned_lead",
        queryset=Employee.objects.all(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Event
        fields = ["assigned_lead_id", "booking_status"]
