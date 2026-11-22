"""Screenshot serialization.

Deliberately never includes the image or a URL to it — `file` is absent from
every field list below. The dedicated `view` action (see `views.py`) is the
only place the actual image bytes are ever returned.
"""

from __future__ import annotations

from rest_framework import serializers

from core.models import AuditLog
from employees.models import Employee

from .models import ScreenshotCapture


class ScreenshotUploadSerializer(serializers.Serializer):
    """Body of `POST /api/agent/screenshot/` — multipart, agent-authenticated.

    `employee`/`computer` are deliberately not fields here: they come from the
    authenticated device (`request.auth`), the same way every other agent
    endpoint resolves identity, rather than from anything the agent's request
    body could claim.
    """

    captured_at = serializers.DateTimeField()
    # A plain FileField, not ImageField: the latter needs Pillow installed on the
    # backend purely to validate upload content, which this project does not
    # otherwise need. Content-type is checked by hand in the view instead.
    file = serializers.FileField()


class _EmployeeStubSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = ["id", "employee_id", "name"]


class ScreenshotCaptureSerializer(serializers.ModelSerializer):
    employee = _EmployeeStubSerializer(read_only=True)
    computer_name = serializers.CharField(source="computer.computer_name", read_only=True)
    view_count = serializers.SerializerMethodField()
    last_viewed_by = serializers.SerializerMethodField()

    class Meta:
        model = ScreenshotCapture
        fields = [
            "id",
            "employee",
            "computer_name",
            "captured_at",
            "view_count",
            "last_viewed_by",
            "created_at",
        ]
        read_only_fields = fields

    def _view_logs(self, obj):
        return AuditLog.objects.filter(
            action=AuditLog.Action.SCREENSHOT_VIEWED_BY_ADMIN,
            target_type="ScreenshotCapture",
            target_id=str(obj.pk),
        ).order_by("-created_at")

    def get_view_count(self, obj):
        return self._view_logs(obj).count()

    def get_last_viewed_by(self, obj):
        entry = self._view_logs(obj).first()
        if entry is None:
            return None
        return {"admin": entry.actor.email if entry.actor else None, "at": entry.created_at}
