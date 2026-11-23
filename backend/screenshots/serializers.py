"""Screenshot serialization.

`image_url` points at the dedicated `view` action (`views.py`) rather than
embedding the file itself: the actual bytes still only ever come from that
one authenticated, admin-only endpoint, this just gives the list/detail
response a link to it instead of making the frontend guess the URL shape.
Viewing is no longer audit-logged (reversed 2026-11-23, by request — admins
review captures as freely as any other report until retention deletes them),
so there is no view-count/last-viewer metadata to surface here either.
"""

from __future__ import annotations

from rest_framework import serializers

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
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ScreenshotCapture
        fields = [
            "id",
            "employee",
            "computer_name",
            "captured_at",
            "image_url",
            "created_at",
        ]
        read_only_fields = fields

    def get_image_url(self, obj):
        request = self.context.get("request")
        url = f"/api/screenshots/{obj.pk}/view/"
        return request.build_absolute_uri(url) if request else url
