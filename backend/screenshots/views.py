"""Screenshot API — admin-facing only.

Visibility is enforced at the permission level (`IsAdminOnly`) since there is
no owner/grantee tier at all for this resource, unlike every other feature in
this codebase.

List/retrieve return metadata only. The dedicated `view` action is the only
place image bytes are ever returned, and every call to it is audit-logged
unconditionally — there is no "expected" owner/grantee view here to exempt,
since every view is an admin exercising access the employee themselves does
not have.
"""

from __future__ import annotations

from django.http import FileResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.throttling import ScopedRateThrottle

from activities.queries import day_window
from activities.views import parse_date
from attendance.models import AppSettings
from core.audit import record
from core.models import AuditLog

from .models import ScreenshotCapture
from .permissions import IsAdminOnly
from .serializers import ScreenshotCaptureSerializer


class ScreenshotCaptureViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve filtered the same way `ActivityViewSet` is — by employee
    and day — so the activity page can show the one day's captures for the
    one employee it is already looking at, not every screenshot ever taken."""

    serializer_class = ScreenshotCaptureSerializer
    permission_classes = [IsAdminOnly]

    def get_queryset(self):
        params = self.request.query_params
        queryset = ScreenshotCapture.objects.select_related("employee", "computer")
        if params.get("employee"):
            queryset = queryset.filter(employee_id=params["employee"])
        if params.get("date"):
            window_start, window_end = day_window(parse_date(params["date"], AppSettings.load()))
            queryset = queryset.filter(captured_at__gte=window_start, captured_at__lt=window_end)
        return queryset

    @action(detail=True, methods=["get"])
    def view(self, request, pk=None):
        capture = self.get_object()
        record(
            actor=request.user,
            action=AuditLog.Action.SCREENSHOT_VIEWED_BY_ADMIN,
            target=capture,
        )
        return FileResponse(capture.file.open("rb"), content_type="image/png")

    def get_throttles(self):
        if self.action == "view":
            self.throttle_scope = "screenshot-view"
            return [ScopedRateThrottle()]
        return super().get_throttles()
