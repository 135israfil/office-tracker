from django.contrib import admin

from .models import Computer


@admin.register(Computer)
class ComputerAdmin(admin.ModelAdmin):
    list_display = ["computer_name", "employee", "status", "agent_version", "last_seen_at"]
    list_filter = ["status"]
    search_fields = ["computer_name", "employee__name", "employee__employee_id"]
    # The token hash is not a secret worth reading, but nothing good comes of editing it
    # by hand either: credentials change through enrolment, never through a form.
    readonly_fields = ["device_token_hash", "registered_at", "last_seen_at"]
