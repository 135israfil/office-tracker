"""Vault entry API.

Visibility is enforced here, in `get_queryset()`, the same way `tasks.views.
TaskViewSet` and `activities.views.resolve_employee` enforce it — not only in
the permission class, so a request for an entry the requester cannot see
404s at the queryset rather than ever reaching an object-level check with a
row to leak.

The decrypted password is returned only by `reveal`, never by list/retrieve
(see serializers.py) — which is what makes this action's throttle scope and
conditional admin-reveal audit logging clean to attach without touching any
other endpoint.

The "pick a coworker to share with" picker reuses `tasks.views.
AssignableEmployeesView` via the frontend's existing `listAssignableEmployees`
call (`/api/tasks/assignable-employees/`) rather than duplicating it here —
its shape (id/employee_id/name, any authenticated user) is already exactly
what this feature needs.
"""

from __future__ import annotations

from django.db.models import Q
from rest_framework import serializers as drf_serializers
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from core.audit import record
from core.models import AuditLog
from employees.models import Employee

from .crypto import decrypt_secret
from .models import VaultEntry, VaultEntryGrant
from .permissions import IsVaultEntryOwnerOrGranteeOrAdmin
from .serializers import VaultEntrySerializer


class VaultEntryViewSet(viewsets.ModelViewSet):
    serializer_class = VaultEntrySerializer
    permission_classes = [IsAuthenticated, IsVaultEntryOwnerOrGranteeOrAdmin]

    def get_queryset(self):
        queryset = VaultEntry.objects.select_related("owner").prefetch_related(
            "grants__grantee", "grants__granted_by"
        )
        user = self.request.user
        if user.is_admin:
            pass
        else:
            employee = getattr(user, "employee", None)
            if employee is None:
                return VaultEntry.objects.none()
            queryset = queryset.filter(Q(owner=employee) | Q(grants__grantee=employee)).distinct()

        # Title/username only — the secret itself is never searchable, the same
        # reason it is never returned by list/retrieve (see serializers.py).
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(Q(title__icontains=search) | Q(username__icontains=search))
        return queryset

    def get_throttles(self):
        # A decrypt action gets its own tighter scope rather than inheriting the
        # blanket 2000/hour "user" rate, following the precedent already set for
        # "login" — the default rate was never meant to cover a decrypt operation.
        if self.action == "reveal":
            self.throttle_scope = "vault-reveal"
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def perform_create(self, serializer):
        employee = getattr(self.request.user, "employee", None)
        if employee is None:
            raise drf_serializers.ValidationError(
                "This account is not linked to an employee record."
            )

        # Optional initial grantees, the same shape and convention
        # tasks.views.TaskViewSet.perform_create uses for "assignees" — lets the
        # frontend share a new entry at creation time, not only afterward.
        raw_ids = self.request.data.get("grantees") or []
        grantees = list(Employee.objects.filter(pk__in=raw_ids))
        if len(grantees) != len(set(raw_ids)):
            raise drf_serializers.ValidationError({"grantees": "One or more employees not found."})

        entry = serializer.save(owner=employee)
        for grantee in grantees:
            VaultEntryGrant.objects.create(entry=entry, grantee=grantee, granted_by=employee)

    def _reserialize(self, entry):
        """Re-fetch an entry fresh for the response after changing its grants.

        Mirrors tasks.views.TaskViewSet._reserialize: get_object() prefetches
        `grants` onto the instance; neither `VaultEntryGrant.objects.create()`
        nor a bare `.filter().delete()` invalidates that cache, so serializing
        the same Python object afterward would silently show the pre-write
        grant list.
        """
        entry = (
            VaultEntry.objects.select_related("owner")
            .prefetch_related("grants__grantee", "grants__granted_by")
            .get(pk=entry.pk)
        )
        return Response(self.get_serializer(entry).data)

    @action(detail=True, methods=["post"])
    def reveal(self, request, pk=None):
        """Return the decrypted password. Logged only when the requester is
        neither the owner nor an explicit grantee — i.e. an admin exercising
        the blanket-visibility override — per the design's resolution of the
        admin-visibility dissent: that access stays disclosed and logged,
        never silent."""
        entry = self.get_object()
        employee = getattr(request.user, "employee", None)
        is_owner = employee is not None and entry.owner_id == employee.id
        is_grantee = employee is not None and entry.grants.filter(grantee=employee).exists()
        if not (is_owner or is_grantee):
            record(
                actor=request.user,
                action=AuditLog.Action.VAULT_ENTRY_REVEALED_BY_ADMIN,
                target=entry,
            )
        return Response({"password": decrypt_secret(entry.secret_ciphertext)})

    @action(detail=True, methods=["post"])
    def share(self, request, pk=None):
        """Add one more grantee. Owner-only, enforced by the permission class."""
        entry = self.get_object()

        try:
            employee = Employee.objects.get(pk=request.data.get("employee"))
        except (Employee.DoesNotExist, ValueError, TypeError):
            return Response({"detail": "No such employee."}, status=400)

        if entry.grants.filter(grantee=employee).exists():
            return Response({"detail": "Already shared with that employee."}, status=400)

        granted_by = getattr(request.user, "employee", None) or entry.owner
        VaultEntryGrant.objects.create(entry=entry, grantee=employee, granted_by=granted_by)
        return self._reserialize(entry)

    @action(detail=True, methods=["delete"], url_path="grants/(?P<employee_id>[^/.]+)")
    def revoke_grant(self, request, pk=None, employee_id=None):
        """Revoke one grantee's access. Self-removal is always allowed;
        revoking someone else is owner-only — enforced by
        `IsVaultEntryOwnerOrGranteeOrAdmin.has_object_permission`'s
        `revoke_grant` branch, not here."""
        entry = self.get_object()
        deleted, _ = entry.grants.filter(grantee_id=employee_id).delete()
        if not deleted:
            return Response(
                {"detail": "That employee does not have access to this entry."}, status=404
            )
        return self._reserialize(entry)
