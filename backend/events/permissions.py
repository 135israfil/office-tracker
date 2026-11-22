"""Event permissions.

An admin's visibility here is mostly a read-only override — an admin may
always retrieve an event, but editing or deleting it is owner-only — except
for two narrow, admin-only slices that work on any event regardless of
ownership: `financials` (budget/document/financial status) and
`coordination` (assigned lead/booking status). Reading a non-owned event
that is not LOCKED is refused one level up, by `EventViewSet.get_queryset()`
filtering it out entirely — this class only ever sees events the queryset
already decided the requester may know about.
"""

from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import EventBookingStatus


def _employee_of(request):
    return getattr(request.user, "employee", None)


class IsEventOwnerOrAdmin(BasePermission):
    message = "You do not have permission to do that on this event."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        employee = _employee_of(request)
        is_owner = employee is not None and obj.owner_id == employee.id

        if view.action in ("financials", "coordination"):
            # Admin-only, regardless of ownership — see events/models.py's module
            # docstring. Not folded into the "update"/"partial_update" branch below:
            # an owner who is not an admin must not be able to set these fields by
            # sending them to the ordinary PATCH endpoint instead.
            return user.is_admin
        if view.action in ("destroy", "update", "partial_update"):
            return is_owner

        if request.method in SAFE_METHODS:
            return is_owner or user.is_admin or obj.booking_status == EventBookingStatus.LOCKED
        return False
