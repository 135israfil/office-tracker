from django.contrib import admin

from .models import ScreenshotCapture


@admin.register(ScreenshotCapture)
class ScreenshotCaptureAdmin(admin.ModelAdmin):
    # `file` is deliberately excluded: Django admin is for operational visibility
    # (who/when/which PC), not a second, unaudited way to view the image itself.
    # Every real view must go through the `view` action, which is logged.
    list_display = ["employee", "computer", "captured_at", "created_at"]
    search_fields = ["employee__name", "employee__employee_id", "computer__computer_name"]
    autocomplete_fields = ["employee", "computer", "activity"]
    exclude = ["file"]
