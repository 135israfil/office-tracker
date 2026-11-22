"""Vault permissions — the fourth distinct permission shape in this codebase,
after `IsAdmin`, `IsAdminOrReadOnlySelf`, and tasks.IsTaskParticipantOrAdmin.

Unlike those, an admin's blanket visibility here is deliberately a read-only
override: an admin may always retrieve/reveal an entry, but editing, deleting,
or managing another employee's shares is owner-only, never admin-by-default.
This is the design's resolution of the brainstorm review's admin-visibility
dissent — blanket access stays, but it is narrower than "full admin
takeover" and (via `views.reveal`) always disclosed and logged.

Object-level checks here are the second gate, not the only one:
`VaultEntryViewSet.get_queryset()` already filters to entries the requester
owns, is granted, or (as admin) can see at all — an uninvolved employee's
request for someone else's entry never reaches `has_object_permission` with
a row to leak.
"""

from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission


def _employee_of(request):
    return getattr(request.user, "employee", None)


class IsVaultEntryOwnerOrGranteeOrAdmin(BasePermission):
    message = "You do not have permission to do that on this vault entry."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        employee = _employee_of(request)
        is_owner = employee is not None and obj.owner_id == employee.id
        is_grantee = employee is not None and obj.grants.filter(grantee=employee).exists()

        if view.action == "destroy":
            return is_owner
        if view.action == "share":
            return is_owner
        if view.action == "revoke_grant":
            # Self-removal is always allowed; revoking someone else is owner-only —
            # the same split as tasks.remove_assignee.
            removed_employee_id = view.kwargs.get("employee_id")
            is_self = employee is not None and str(employee.id) == str(removed_employee_id)
            return is_owner or is_self
        if view.action in ("update", "partial_update"):
            return is_owner
        if view.action == "reveal":
            return is_owner or is_grantee or user.is_admin

        if request.method in SAFE_METHODS:
            return is_owner or is_grantee or user.is_admin
        return False
