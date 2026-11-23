"""In-app notifications: a task assignment, a task's status changing, an
event becoming LOCKED, or an event's alert date arriving. Polled by the
frontend and surfaced there as a browser `Notification` — there is no push
infrastructure (no service worker, no email backend) behind this, matching
every other deferred-notification decision already made in this codebase
(see docs/designs/task-tracking.md).
"""

from __future__ import annotations

from django.db import models

from employees.models import Employee


class Notification(models.Model):
    recipient = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="notifications")
    message = models.CharField(max_length=255)
    # Relative frontend path the notification is about, e.g. "/tasks/5". Blank
    # is valid — not every notification needs somewhere to click through to.
    url = models.CharField(max_length=200, blank=True)
    # Set only by the daily alert-date reminder, to avoid sending the same
    # reminder twice if the command is ever run more than once on the same
    # day — unique when set; NULL never collides with another NULL.
    dedupe_key = models.CharField(max_length=100, blank=True, null=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["recipient", "read_at"])]

    def __str__(self):
        return self.message
