"""Event calendar: personal by default, optionally shared with named
coworkers. No company-wide visibility in this iteration (see docs/designs/
event-calendar.md) — every visibility rule here is two-tier only: owner, or
an explicit named grantee (plus the admin override).

Sharing is an explicit through-model (`EventGrant`), not a bare
`ManyToManyField`, for the same reason `vault.VaultEntryGrant` and
`tasks.TaskAssignee` are: per-grant state (who granted it, when) is needed
from day one. A grant is visibility only — there is no accept/decline/RSVP
state, and this is deliberate: it should not grow into an invitation
workflow later without that being a conscious decision.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from employees.models import Employee


class EventStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    CANCELLED = "CANCELLED", "Cancelled"


class EventPhase(models.TextChoices):
    UPCOMING = "UPCOMING", "Upcoming"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    PAST = "PAST", "Past"


def event_phase(start, end, now) -> str:
    """Pure: where `now` falls relative to an event's start/end.

    Explicitly three-state, unlike `tasks.task_is_overdue`'s binary
    threshold — an event has a start *and* optional end, not a single
    deadline date. Kept free of its own clock, the same convention
    `task_is_overdue` and `activities.queries` follow, so this is testable
    against fabricated instants rather than hoped about.
    """
    if now < start:
        return EventPhase.UPCOMING
    if end is not None and start <= now <= end:
        return EventPhase.IN_PROGRESS
    return EventPhase.PAST


class Event(models.Model):
    # PROTECT, not CASCADE: an employee record must not silently take every
    # event they ever created with it if it is ever removed — a grantee may
    # still be relying on a shared event's continued existence.
    owner = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="events")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start = models.DateTimeField()
    end = models.DateTimeField(null=True, blank=True)
    all_day = models.BooleanField(default=False)
    location = models.CharField(max_length=200, blank=True)
    status = models.CharField(
        max_length=16, choices=EventStatus.choices, default=EventStatus.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start", "id"]
        indexes = [
            models.Index(fields=["owner"]),
            models.Index(fields=["start"]),
        ]

    def __str__(self):
        return self.title

    def clean(self):
        if self.end is not None and self.end < self.start:
            raise ValidationError({"end": "An event cannot end before it starts."})

    @property
    def phase(self) -> str:
        return event_phase(self.start, self.end, timezone.now())


class EventGrant(models.Model):
    """One employee's view-only access to one event — the through-model for
    `Event.grants`."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="grants")
    grantee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="event_grants")
    # PROTECT: who granted access is part of this event's history and must
    # not be erased by that person's own employee record being removed later.
    granted_by = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="event_grants_made"
    )
    granted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["granted_at"]
        constraints = [
            models.UniqueConstraint(fields=["event", "grantee"], name="unique_grant_per_event")
        ]
        indexes = [
            models.Index(fields=["grantee", "event"]),
        ]

    def __str__(self):
        return f"event {self.event_id} -> employee {self.grantee_id}"
