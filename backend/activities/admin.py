from django.contrib import admin

from .models import Activity


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = [
        "computer",
        "employee",
        "activity_type",
        "start_time",
        "end_time",
        "duration_seconds",
    ]
    list_filter = ["activity_type", "closed_by_server"]
    search_fields = ["employee__name", "computer__computer_name", "application_name"]
    date_hierarchy = "start_time"
