"""Event permissions, modeled directly on
`vault.permissions.IsVaultEntryOwnerOrGranteeOrAdmin`.

An admin's visibility here is, like the Vault's, a deliberately narrow,
read-only override: an admin may always retrieve an event, but editing,
deleting, cancelling, or managing another employee's shares is owner-only.

Object-level checks here are the second gate, not the only one:
`EventViewSet.get_queryset()` already filters to events the requester
owns, is granted, or (as admin) can see at all.
"""

from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission


def _employee_of(request):
    return getattr(request.user, "employee", None)


class IsEventOwnerOrGranteeOrAdmin(BasePermission):
    message = "You do not have permission to do that on this event."

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
            removed_employee_id = view.kwargs.get("employee_id")
            is_self = employee is not None and str(employee.id) == str(removed_employee_id)
            return is_owner or is_self
        if view.action in ("update", "partial_update"):
            return is_owner

        if request.method in SAFE_METHODS:
            return is_owner or is_grantee or user.is_admin
        return False
