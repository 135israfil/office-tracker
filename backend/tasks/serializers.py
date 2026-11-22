"""Task and sub-task serialization.

`assignees` is read-only here: assignment is managed through `TaskViewSet`'s dedicated
`add_assignee`/`remove_assignee` actions, not by editing the list in place, so each
change can be checked against its own permission rule (self-removal is always allowed;
removing someone else is creator/admin-only) rather than one rule covering a whole list
replacement.
"""

from __future__ import annotations

from rest_framework import serializers

from employees.models import Employee

from .models import Task, TaskAssignee


class _EmployeeStubSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = ["id", "employee_id", "name"]


class TaskAssigneeSerializer(serializers.ModelSerializer):
    employee = _EmployeeStubSerializer(read_only=True)
    assigned_by = _EmployeeStubSerializer(read_only=True)

    class Meta:
        model = TaskAssignee
        fields = ["id", "employee", "assigned_by", "assigned_at"]
        read_only_fields = fields


class TaskSerializer(serializers.ModelSerializer):
    is_overdue = serializers.BooleanField(read_only=True)
    created_by = _EmployeeStubSerializer(read_only=True)
    assignees = TaskAssigneeSerializer(many=True, read_only=True)
    parent_stub = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            "id",
            "title",
            "description",
            "status",
            "deadline",
            "is_overdue",
            "created_by",
            "assignees",
            "parent",
            "parent_stub",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_by",
            "assignees",
            "is_overdue",
            "created_at",
            "updated_at",
        ]

    def get_parent_stub(self, obj):
        if obj.parent_id is None:
            return None
        # A stub only — id and title, never the full parent row — regardless of whether
        # the viewer can see the parent task in full (see the design's Technical Plan).
        return {"id": obj.parent_id, "title": obj.parent.title}

    def validate_parent(self, value):
        if value is not None and value.parent_id is not None:
            raise serializers.ValidationError("A sub-task cannot itself have sub-tasks.")
        return value
