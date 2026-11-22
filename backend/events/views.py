"""Event API.

Visibility is enforced here, in `get_queryset()`, the same way
`vault.views.VaultEntryViewSet` and `tasks.views.TaskViewSet` enforce it.

Unlike the Vault, there is no separate "reveal" action — nothing here is
encrypted, so the ordinary `retrieve` is the action that matters for
disclosure. `retrieve` is overridden to conditionally audit-log an admin's
view of a non-shared event; `list` deliberately never logs, since browsing
a calendar is a routine, frequent action unlike the Vault's occasional,
deliberate `reveal` of a secret — logging every list row would flood the
audit log in a way the Vault's pattern never does.
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
from employees.models import Employee

from .models import Event, EventGrant
from .permissions import IsEventOwnerOrGranteeOrAdmin
from .serializers import EventSerializer


class EventViewSet(viewsets.ModelViewSet):
    serializer_class = EventSerializer
    permission_classes = [IsAuthenticated, IsEventOwnerOrGranteeOrAdmin]

    def get_queryset(self):
        queryset = Event.objects.select_related("owner").prefetch_related(
            "grants__grantee", "grants__granted_by"
        )
        user = self.request.user
        if user.is_admin:
            return queryset
        employee = getattr(user, "employee", None)
        if employee is None:
            return Event.objects.none()
        return queryset.filter(Q(owner=employee) | Q(grants__grantee=employee)).distinct()

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
        is_grantee = employee is not None and event.grants.filter(grantee=employee).exists()
        if not (is_owner or is_grantee):
            record(actor=request.user, action=AuditLog.Action.EVENT_VIEWED_BY_ADMIN, target=event)
        return Response(self.get_serializer(event).data)

    def _reserialize(self, event):
        """Re-fetch an event fresh for the response after changing its
        grants — mirrors vault.views.VaultEntryViewSet._reserialize."""
        event = (
            Event.objects.select_related("owner")
            .prefetch_related("grants__grantee", "grants__granted_by")
            .get(pk=event.pk)
        )
        return Response(self.get_serializer(event).data)

    @action(detail=True, methods=["post"])
    def share(self, request, pk=None):
        """Add one more grantee. Owner-only, enforced by the permission class."""
        event = self.get_object()

        try:
            employee = Employee.objects.get(pk=request.data.get("employee"))
        except (Employee.DoesNotExist, ValueError, TypeError):
            return Response({"detail": "No such employee."}, status=400)

        if event.grants.filter(grantee=employee).exists():
            return Response({"detail": "Already shared with that employee."}, status=400)

        granted_by = getattr(request.user, "employee", None) or event.owner
        EventGrant.objects.create(event=event, grantee=employee, granted_by=granted_by)
        return self._reserialize(event)

    @action(detail=True, methods=["delete"], url_path="grants/(?P<employee_id>[^/.]+)")
    def revoke_grant(self, request, pk=None, employee_id=None):
        """Revoke one grantee's access. Self-removal is always allowed;
        revoking someone else is owner-only — enforced by
        `IsEventOwnerOrGranteeOrAdmin.has_object_permission`'s
        `revoke_grant` branch, not here."""
        event = self.get_object()
        deleted, _ = event.grants.filter(grantee_id=employee_id).delete()
        if not deleted:
            return Response(
                {"detail": "That employee does not have access to this event."}, status=404
            )
        return self._reserialize(event)
