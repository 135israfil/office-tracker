from django.contrib import admin

from .models import Employee, EmployeeShift, LeaveAdjustment


class EmployeeShiftInline(admin.TabularInline):
    model = EmployeeShift
    extra = 0


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ["employee_id", "name", "department", "status", "leave_total", "leave_used"]
    list_filter = ["status", "department"]
    search_fields = ["employee_id", "name", "user__email"]
    inlines = [EmployeeShiftInline]


@admin.register(LeaveAdjustment)
class LeaveAdjustmentAdmin(admin.ModelAdmin):
    list_display = ["employee", "target", "delta", "reason", "created_by", "created_at"]
    list_filter = ["target"]
