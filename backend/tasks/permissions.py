"""Task permissions — the first resource in this codebase an ordinary employee can
write to on someone else's behalf, not only their own.

`IsAdmin` and `IsAdminOrReadOnlySelf` both assume an employee is either locked out
entirely or read-only of their own data. Neither fits a resource where any employee may
create a task and any assignee may act on it, so this is a new shape, not a reuse.

Object-level checks here are the second gate, not the only one: `TaskViewSet.
get_queryset()` already filters to tasks the requester created or is assigned to, so an
uninvolved employee's request for someone else's task never reaches `has_object_
permission` with a row to leak — it 404s at the queryset instead. What this class adds is
the finer-grained rule within a task someone *can* see: delete is creator/admin-only, and
setting status to CANCELLED is creator/admin-only too.
"""

from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import TaskStatus


def _employee_of(request):
    return getattr(request.user, "employee", None)


class IsTaskParticipantOrAdmin(BasePermission):
    message = "You do not have permission to do that on this task."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        # Any authenticated user may list/create/retrieve/update — object-level checks
        # below, and the queryset's own visibility filter, do the rest.
        return True

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_admin:
            return True

        employee = _employee_of(request)
        if employee is None:
            return False

        is_creator = obj.created_by_id == employee.id
        is_assignee = obj.assignees.filter(employee=employee).exists()

        # Branched on view.action rather than request.method: the nested
        # remove_assignee action also uses DELETE, but "remove one assignee" and
        # "delete the whole task" are different rules (self-removal is always
        # allowed for the former; only the creator may do the latter).
        if view.action == "destroy":
            return is_creator

        if view.action == "remove_assignee":
            removed_employee_id = view.kwargs.get("employee_id")
            is_self = str(employee.id) == str(removed_employee_id)
            return is_creator or is_self

        if request.method in SAFE_METHODS:
            return is_creator or is_assignee

        # Any other write (update/partial_update/add_assignee): creator or assignee
        # may act, except that cancelling the task is reserved for the creator — an
        # assignee should not be able to unilaterally kill work someone else asked for.
        if not (is_creator or is_assignee):
            return False
        if (
            view.action in ("update", "partial_update")
            and request.data.get("status") == TaskStatus.CANCELLED
            and not is_creator
        ):
            return False
        return True
