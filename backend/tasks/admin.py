from django.contrib import admin

from .models import Task, TaskAssignee


class TaskAssigneeInline(admin.TabularInline):
    model = TaskAssignee
    extra = 0
    autocomplete_fields = ["employee", "assigned_by"]


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ["title", "status", "created_by", "parent", "deadline", "created_at"]
    list_filter = ["status"]
    search_fields = ["title", "created_by__name", "created_by__employee_id"]
    autocomplete_fields = ["created_by", "parent"]
    inlines = [TaskAssigneeInline]


@admin.register(TaskAssignee)
class TaskAssigneeAdmin(admin.ModelAdmin):
    list_display = ["task", "employee", "assigned_by", "assigned_at"]
    autocomplete_fields = ["task", "employee", "assigned_by"]
