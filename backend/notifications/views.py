"""Notification API — read-only plus two tiny write actions (mark one/all
read). Nothing creates a notification through this API; every notification is
written server-side by `notifications.services.notify`, called from the
feature that caused it (see `tasks/views.py`, `events/views.py`, and
`events/management/commands/send_event_alerts.py`).
"""

from __future__ import annotations

from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification
from .serializers import NotificationSerializer


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        employee = getattr(self.request.user, "employee", None)
        if employee is None:
            return Notification.objects.none()
        queryset = Notification.objects.filter(recipient=employee)
        if self.request.query_params.get("unread") == "true":
            queryset = queryset.filter(read_at__isnull=True)
        return queryset

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        notification = self.get_object()
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])
        return Response(self.get_serializer(notification).data)

    @action(detail=False, methods=["post"])
    def read_all(self, request):
        self.get_queryset().filter(read_at__isnull=True).update(read_at=timezone.now())
        return Response(status=204)
