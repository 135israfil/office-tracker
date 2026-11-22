"""Event API.

Visibility is enforced here, in `get_queryset()`: the owner always sees
their own event, an admin sees every event, and any other employee sees it
only once it is LOCKED — see `models.py`'s module docstring. `retrieve` is
overridden to audit-log an admin's view of an event they do not own; `list`
deliberately never logs, since browsing is a routine, frequent action.
"""

from __future__ import annotations

from django.db.models import Q
from rest_framework import serializers as drf_serializers
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.audit import record
from core.models import AuditLog

from .models import Event, EventBookingStatus
from .permissions import IsEventOwnerOrAdmin
from .serializers import EventCoordinationSerializer, EventFinancialsSerializer, EventSerializer


class EventViewSet(viewsets.ModelViewSet):
    serializer_class = EventSerializer
    permission_classes = [IsAuthenticated, IsEventOwnerOrAdmin]

    def get_queryset(self):
        queryset = Event.objects.select_related("owner", "assigned_lead")
        user = self.request.user
        if user.is_admin:
            return queryset
        employee = getattr(user, "employee", None)
        if employee is None:
            return Event.objects.none()
        return queryset.filter(Q(owner=employee) | Q(booking_status=EventBookingStatus.LOCKED))

    def perform_create(self, serializer):
        employee = getattr(self.request.user, "employee", None)
        if employee is None:
            raise drf_serializers.ValidationError(
                "This account is not linked to an employee record."
            )
        serializer.save(owner=employee)

    def retrieve(self, request, *args, **kwargs):
        event = self.get_object()
        employee = getattr(request.user, "employee", None)
        is_owner = employee is not None and event.owner_id == employee.id
        if request.user.is_admin and not is_owner:
            record(actor=request.user, action=AuditLog.Action.EVENT_VIEWED_BY_ADMIN, target=event)
        return Response(self.get_serializer(event).data)

    @action(detail=True, methods=["patch"])
    def financials(self, request, pk=None):
        """Set the admin-only budget/document/financial-status fields.
        Permission (admin-only, any event) is enforced entirely by
        `IsEventOwnerOrAdmin.has_object_permission`'s `financials`
        branch — this action does not re-check ownership."""
        event = self.get_object()
        serializer = EventFinancialsSerializer(event, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(self.get_serializer(event).data)

    @action(detail=True, methods=["patch"])
    def coordination(self, request, pk=None):
        """Set the lead/booking-status fields on any event, regardless of
        ownership. Permission is enforced entirely by
        `IsEventOwnerOrAdmin.has_object_permission`'s `coordination`
        branch — this action does not re-check ownership. The owner still
        sets these same two fields through the ordinary `update`."""
        event = self.get_object()
        serializer = EventCoordinationSerializer(event, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(self.get_serializer(event).data)
