"""Permission for agent endpoints."""

from rest_framework.permissions import BasePermission

from .models import Computer


class IsRegisteredDevice(BasePermission):
    """Allow only requests carrying a valid device token.

    Checks `request.auth` rather than just `is_authenticated`: a logged-in employee's
    browser session must not be able to post heartbeats for a machine.
    """

    message = "A valid device token is required."

    def has_permission(self, request, view):
        return isinstance(request.auth, Computer)
