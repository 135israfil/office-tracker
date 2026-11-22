"""Periodic screenshot capture of a tracked PC (README.txt §31, reversed for
screenshots specifically on 2026-11-22 — see docs/designs/
screenshot-based-activity-tracking.md).

A dedicated app, not a field on `Activity`: `Activity`'s schema is
deliberately interval-shaped (`start_time`/`end_time`) to keep per-PC row
counts low, and a screenshot is a point-in-time, file-backed artifact with
no interval semantics — grafting it on would reintroduce exactly the
per-sample row growth that schema was built to avoid.

Admin/HR only, by design — unlike every other feature in this codebase,
the employee a capture is *of* never sees the image itself, only that it
was viewed and by whom (see `views.py`).
"""

from __future__ import annotations

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models

from computers.models import Computer
from employees.models import Employee

# A second, dedicated FileSystemStorage instance, never the project's `default`
# storage: this directory is never served by whitenoise/STATIC_ROOT or any
# public URL. The only way to read a file back is the `view` action, which
# audits every call.
screenshot_storage = FileSystemStorage(location=settings.SCREENSHOT_STORAGE_ROOT)


class ScreenshotCapture(models.Model):
    # PROTECT, not CASCADE: the same choice every other owner/creator FK in this
    # codebase makes, so a capture is never silently stranded or destroyed by an
    # employee/computer record being removed.
    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="screenshot_captures"
    )
    computer = models.ForeignKey(
        Computer, on_delete=models.PROTECT, related_name="screenshot_captures"
    )
    # Nullable + SET_NULL: this and the Activity it was captured during have
    # independent retention windows, so neither record should block or
    # cascade-delete the other if one purges first.
    activity = models.ForeignKey(
        "activities.Activity",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="screenshot_captures",
    )
    captured_at = models.DateTimeField()
    file = models.FileField(upload_to="screenshots/%Y/%m/%d/", storage=screenshot_storage)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-captured_at", "-id"]
        indexes = [
            models.Index(fields=["employee"]),
            models.Index(fields=["captured_at"]),
        ]

    def __str__(self):
        return f"screenshot of {self.employee_id} at {self.captured_at:%Y-%m-%d %H:%M}"
