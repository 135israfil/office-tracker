"""Cross-cutting models.

The audit log lives here rather than in its own app: §33 does not list an audit app, and
it is written to by every other app, so a shared home avoids circular imports.
"""

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Append-only record of admin actions, required by §30.

    Never updated and never deleted by application code. `actor` is nullable so that
    removing a user account cannot erase the history of what that account did.
    """

    class Action(models.TextChoices):
        EMPLOYEE_CREATED = "EMPLOYEE_CREATED", "Employee created"
        EMPLOYEE_UPDATED = "EMPLOYEE_UPDATED", "Employee updated"
        EMPLOYEE_DISABLED = "EMPLOYEE_DISABLED", "Employee disabled"
        EMPLOYEE_ENABLED = "EMPLOYEE_ENABLED", "Employee enabled"
        SHIFTS_UPDATED = "SHIFTS_UPDATED", "Employee shifts updated"
        LEAVE_ADJUSTED = "LEAVE_ADJUSTED", "Leave balance adjusted"
        SETTINGS_UPDATED = "SETTINGS_UPDATED", "Settings updated"
        HOLIDAY_CREATED = "HOLIDAY_CREATED", "Holiday created"
        HOLIDAY_UPDATED = "HOLIDAY_UPDATED", "Holiday updated"
        HOLIDAY_DELETED = "HOLIDAY_DELETED", "Holiday deleted"
        ATTENDANCE_CORRECTED = "ATTENDANCE_CORRECTED", "Attendance corrected"
        DEVICE_CREATED = "DEVICE_CREATED", "Computer enrolled"
        DEVICE_CODE_ISSUED = "DEVICE_CODE_ISSUED", "Enrollment code issued"
        DEVICE_REGISTERED = "DEVICE_REGISTERED", "Device registered"
        DEVICE_ENABLED = "DEVICE_ENABLED", "Device enabled"
        DEVICE_DISABLED = "DEVICE_DISABLED", "Device disabled"
        # A report export is a read, and reads are not normally audited. This one is:
        # it takes the whole workforce's attendance and activity out of the system in a
        # file that then travels on its own.
        REPORT_EXPORTED = "REPORT_EXPORTED", "Report exported"
        # Written on every retention run, including runs that deleted nothing — "the
        # job ran and found nothing" and "the job did not run" are different facts, and
        # a delete job nobody can reconstruct afterwards is a liability (D5).
        ACTIVITY_PURGED = "ACTIVITY_PURGED", "Activity purged by retention job"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_entries",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    target_type = models.CharField(max_length=40, blank=True)
    target_id = models.CharField(max_length=40, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["target_type", "target_id"]),
        ]

    def __str__(self):
        who = self.actor.email if self.actor else "<deleted user>"
        return f"{self.created_at:%Y-%m-%d %H:%M} {who} {self.action}"
