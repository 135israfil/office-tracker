"""Event declaration: a venue/agency booking owned by its creator.

Visibility is company-wide once an event is locked in, not grant-based: the
owner always sees their own event regardless of status, an admin sees every
event, and any other employee sees it only once `booking_status` is LOCKED
(see `views.py`'s `get_queryset` and `permissions.py`) — there is no
per-employee sharing list to manage.

Budget, document status and financial status are admin-only: the owner (who
may be a plain employee) declares and tracks the booking itself, but only an
admin ever sees or sets the money/paperwork fields, regardless of who owns
the event — enforced in `serializers.py` (read visibility) and `views.py`'s
dedicated `financials` action (write access), not by the owner-based rule
every other field follows.

`assigned_lead` and `booking_status` are a second, narrower admin override,
through `views.py`'s dedicated `coordination` action: any admin may set who
is leading an event and how locked-in it is, the same regardless-of-owner
pattern `financials` uses — everything else (title, agency/venue, setup,
alert date) stays owner-only.

There is deliberately no separate lifecycle status (no draft/active/
cancelled): `booking_status` (on communication / locked / done) already
answers "where is this event at", and a second status field answering the
same question would just be two sources of truth to keep in sync.
"""

from __future__ import annotations

from django.db import models

from employees.models import Employee


class EventBookingStatus(models.TextChoices):
    ON_COMMUNICATION = "ON_COMMUNICATION", "On communication"
    LOCKED = "LOCKED", "Locked"
    DONE = "DONE", "Done"


class EventDocumentStatus(models.TextChoices):
    VERBAL_COMMUNICATION = "VERBAL_COMMUNICATION", "Verbal communication"
    PROPOSAL_SENT = "PROPOSAL_SENT", "Proposal sent"
    WORK_ORDER = "WORK_ORDER", "Work order"
    VERBAL_CONFIRMATION = "VERBAL_CONFIRMATION", "Verbal confirmation"
    INVOICE_SENT = "INVOICE_SENT", "Invoice sent"


class EventFinancialStatus(models.TextChoices):
    ADVANCE = "ADVANCE", "Advance"
    PARTIAL_PAID = "PARTIAL_PAID", "Partial paid"
    FULL_PAID = "FULL_PAID", "Full paid"


class Event(models.Model):
    # PROTECT: an employee record must not silently take every event they
    # ever created with it if it is ever removed.
    owner = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="events")
    title = models.CharField(max_length=200)
    agency_name = models.CharField(max_length=200, blank=True)
    venue_name = models.CharField(max_length=200, blank=True)
    # Rich text (HTML from the frontend's editor), not a single line — no
    # length cap for the same reason `description` fields elsewhere are TextField.
    setup = models.TextField(blank=True)
    # PROTECT, like `owner`: a lead's own employee record must not silently take
    # every event they were ever assigned to with it if it is ever removed.
    assigned_lead = models.ForeignKey(
        Employee,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="led_events",
    )
    booking_status = models.CharField(
        max_length=20,
        choices=EventBookingStatus.choices,
        default=EventBookingStatus.ON_COMMUNICATION,
    )
    alert_on = models.DateField(null=True, blank=True)
    # Admin-only, see the module docstring.
    budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    document_status = models.CharField(
        max_length=24, choices=EventDocumentStatus.choices, blank=True
    )
    financial_status = models.CharField(
        max_length=16, choices=EventFinancialStatus.choices, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Soonest alert first; an event with no alert date sorts last, not first.
        ordering = ["alert_on", "id"]
        indexes = [
            models.Index(fields=["owner"]),
            models.Index(fields=["alert_on"]),
            models.Index(fields=["booking_status"]),
        ]

    def __str__(self):
        return self.title
