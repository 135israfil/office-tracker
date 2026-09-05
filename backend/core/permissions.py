"""Role-based permissions (§29, §30).

Employee data isolation is enforced at the queryset level in each viewset rather than
only here, so a view that forgets a permission class still cannot leak another
employee's records. These classes are the outer gate, not the only one.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsAdmin(BasePermission):
    """Admin-only access."""

    message = "Administrator access is required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_admin)


class IsAdminOrReadOnlySelf(BasePermission):
    """Admins get full access; authenticated employees get read-only access.

    Object-level ownership is still checked by the view's queryset.
    """

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_admin:
            return True
        return request.method in SAFE_METHODS
