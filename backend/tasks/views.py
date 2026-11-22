"""Task API.

Visibility is enforced here, in `get_queryset()`, the same way `activities.views.
resolve_employee` enforces it for activity data — not only in the permission class, so a
request for a task an employee is not involved in 404s at the queryset rather than ever
reaching an object-level check with a row to leak.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Q
from rest_framework import serializers as drf_serializers
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from employees.models import Employee, EmployeeStatus

from .models import Task, TaskAssignee
from .permissions import IsTaskParticipantOrAdmin
from .serializers import TaskSerializer


class AssignableEmployeesView(APIView):
    """Who an authenticated user may assign a task to.

    `EmployeeViewSet` is admin-only and exposes full HR fields (leave balances, phone,
    designation) — exactly wrong for "any employee can see who exists to assign a task
    to," which this feature needs for the first time in this codebase. This is
    deliberately separate and deliberately minimal: an id, an employee_id and a name,
    nothing else, open to anyone authenticated rather than admins only.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        employees = Employee.objects.filter(status=EmployeeStatus.ACTIVE).order_by("name")
        return Response(
            [{"id": e.id, "employee_id": e.employee_id, "name": e.name} for e in employees]
        )


class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated, IsTaskParticipantOrAdmin]

    def get_queryset(self):
        queryset = Task.objects.select_related("created_by", "parent").prefetch_related(
            "assignees__employee", "assignees__assigned_by"
        )

        user = self.request.user
        if not user.is_admin:
            employee = getattr(user, "employee", None)
            if employee is None:
                return Task.objects.none()
            queryset = queryset.filter(
                Q(created_by=employee) | Q(assignees__employee=employee)
            ).distinct()

        # The "top-level only by default" rule is a LIST concern — a sub-task is
        # normally reached through its parent rather than mixed into the general
        # list — not a retrieve/update/delete one. Applying it unconditionally
        # 404s a sub-task's own detail page, since a plain GET /tasks/<id>/ never
        # carries a ?parent= param. Every other action (retrieve, update, destroy,
        # add_assignee, remove_assignee) must see the full set it's otherwise
        # entitled to, unfiltered by parentage.
        if self.action != "list":
            return queryset

        params = self.request.query_params
        if "parent" in params:
            # Sub-tasks of one specific task, e.g. the task's own detail page.
            queryset = queryset.filter(parent_id=params["parent"] or None)
        else:
            queryset = queryset.filter(parent__isnull=True)
        return queryset

    @transaction.atomic
    def perform_create(self, serializer):
        employee = getattr(self.request.user, "employee", None)
        if employee is None:
            raise drf_serializers.ValidationError(
                "This account is not linked to an employee record."
            )

        # The serializer's parent field only validates the one-level-depth rule, not
        # who may use a given task as a parent — without this, anyone could attach a
        # sub-task to a task they have no relationship to at all, just by knowing its
        # id, since parent isn't scoped to the requester's visible queryset.
        parent = serializer.validated_data.get("parent")
        if parent is not None and not self.request.user.is_admin:
            is_involved = (
                parent.created_by_id == employee.id
                or parent.assignees.filter(employee=employee).exists()
            )
            if not is_involved:
                raise drf_serializers.ValidationError(
                    {"parent": "You can only add sub-tasks to a task you can already see."}
                )

        raw_ids = self.request.data.get("assignees") or []
        assignees = list(Employee.objects.filter(pk__in=raw_ids))
        if len(assignees) != len(set(raw_ids)):
            raise drf_serializers.ValidationError({"assignees": "One or more employees not found."})

        task = serializer.save(created_by=employee)
        for assignee in assignees:
            TaskAssignee.objects.create(task=task, employee=assignee, assigned_by=employee)

    def _reserialize(self, task):
        """Re-fetch a task fresh for the response after changing its assignees.

        `get_object()` prefetches `assignees` onto the instance; neither
        `TaskAssignee.objects.create()` nor a bare `.filter().delete()` invalidates
        that cache, so serializing the same Python object afterward would silently
        show the pre-write assignee list. Deliberately bypasses the user-scoped
        visibility queryset: permission was already checked by `get_object()` before
        either action ran, and re-applying that filter here would 404 someone who
        just removed themselves as their task's only assignee, right after their own
        successful request.
        """
        task = (
            Task.objects.select_related("created_by", "parent")
            .prefetch_related("assignees__employee", "assignees__assigned_by")
            .get(pk=task.pk)
        )
        return Response(self.get_serializer(task).data)

    @action(detail=True, methods=["post"])
    def add_assignee(self, request, pk=None):
        """Add one more assignee. Open to the creator or any current assignee."""
        task = self.get_object()

        try:
            employee = Employee.objects.get(pk=request.data.get("employee"))
        except (Employee.DoesNotExist, ValueError, TypeError):
            return Response({"detail": "No such employee."}, status=400)

        if task.assignees.filter(employee=employee).exists():
            return Response({"detail": "Already assigned."}, status=400)

        assigned_by = getattr(request.user, "employee", None) or task.created_by
        TaskAssignee.objects.create(task=task, employee=employee, assigned_by=assigned_by)
        return self._reserialize(task)

    @action(detail=True, methods=["delete"], url_path="assignees/(?P<employee_id>[^/.]+)")
    def remove_assignee(self, request, pk=None, employee_id=None):
        """Remove one assignee. Self-removal is always allowed; removing someone
        else requires being the creator or an admin — enforced by
        `IsTaskParticipantOrAdmin.has_object_permission`'s `remove_assignee` branch,
        not here."""
        task = self.get_object()
        deleted, _ = task.assignees.filter(employee_id=employee_id).delete()
        if not deleted:
            return Response({"detail": "That employee is not assigned to this task."}, status=404)
        return self._reserialize(task)
