"""Task tracking: creating, assigning and breaking work into sub-tasks.

Two rules shape the schema, both decided to avoid a breaking migration later:

* **Sub-tasks are capped at one level.** A `Task` may be set as another task's
  `parent` only if its own `parent` is `None` — enforced in `clean()`. This
  keeps every visibility query flat (no recursive CTE, which Django does not
  support natively) and, as a side effect, makes a cycle structurally
  impossible: a cycle would require a root task to become a sub-task of its
  own child, which this rule rules out outright.
* **Assignees are an explicit through-model, not a bare `ManyToManyField`.**
  Multi-assignee features reliably grow a need for per-assignee state (who
  assigned whom, when); converting a bare M2M to a through-model later would
  touch every caller of `.add()`/`.set()`.

Visibility is enforced in the view's queryset (`Q(created_by=employee) |
Q(assignees__employee=employee)`), the same place `activities.views.
resolve_employee` enforces it for activity data — not only in the permission
class, so a view that forgets a permission check still cannot leak.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from employees.models import Employee


class TaskStatus(models.TextChoices):
    TODO = "TODO", "To do"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    BLOCKED = "BLOCKED", "Blocked"
    DONE = "DONE", "Done"
    CANCELLED = "CANCELLED", "Cancelled"


def task_is_overdue(deadline, status, today) -> bool:
    """Pure: whether a task counts as overdue, given today's office-local date.

    Kept free of its own clock, the same way activities.queries keeps its date
    arithmetic clock-free — that is what lets this be tested against fabricated dates
    instead of hoped about. `Task.is_overdue` below is the thin, DB-touching wrapper
    that supplies the real "today".
    """
    if deadline is None or status in (TaskStatus.DONE, TaskStatus.CANCELLED):
        return False
    return deadline < today


class Task(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=TaskStatus.choices, default=TaskStatus.TODO)
    # A bare date, not a timestamp: "due by end of day", evaluated against the office-
    # local date the same way attendance decides which date a punch belongs to.
    deadline = models.DateField(null=True, blank=True)
    # PROTECT, not CASCADE: an employee record must not silently take every task they
    # ever created with it if it is ever removed.
    created_by = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="tasks_created")
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="subtasks"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["created_by"]),
            models.Index(fields=["parent"]),
        ]

    def __str__(self):
        return self.title

    def clean(self):
        if self.parent_id and self.parent.parent_id is not None:
            raise ValidationError({"parent": "A sub-task cannot itself have sub-tasks."})

    @property
    def is_overdue(self) -> bool:
        """True once the office-local date has passed an open task's deadline.

        Read-time only: this is visibility, not an alert, since nothing in this
        codebase can push a notification yet. See `task_is_overdue` for the actual
        rule; this just supplies it with today's office-local date.
        """
        # Imported here rather than at module level: it pulls in the attendance app,
        # and importing it lazily avoids any import-order sensitivity between apps.
        from attendance.calendar_rules import local_date
        from attendance.models import AppSettings

        today = local_date(timezone.now(), AppSettings.load())
        return task_is_overdue(self.deadline, self.status, today)


class TaskAssignee(models.Model):
    """One employee's assignment to one task — the through-model for `Task.assignees`."""

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="assignees")
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="task_assignments"
    )
    # PROTECT: who assigned a task is part of its history and must not be erased by
    # that person's own employee record being removed later.
    assigned_by = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="assignments_made"
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["assigned_at"]
        constraints = [
            models.UniqueConstraint(fields=["task", "employee"], name="unique_assignee_per_task")
        ]
        indexes = [
            models.Index(fields=["employee", "task"]),
        ]

    def __str__(self):
        return f"task {self.task_id} -> employee {self.employee_id}"
