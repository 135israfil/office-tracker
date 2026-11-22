"""Screenshot permissions: admin-only, full stop.

No owner/grantee tier at all, unlike every other feature in this codebase —
the employee a capture is of never gets API access to it, by design.
"""

from __future__ import annotations

from rest_framework.permissions import BasePermission


class IsAdminOnly(BasePermission):
    message = "Administrator access is required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_admin)
