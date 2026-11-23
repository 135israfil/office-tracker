"""Notify an event's owner and assigned lead on its alert date.

Run once a day from cron or Task Scheduler:

    python manage.py send_event_alerts
    python manage.py send_event_alerts --date 2026-12-01

Deliberately a management command rather than a background job queue, the
same reasoning `mark_absentees` and `mark_offline_computers` already follow
in this codebase — this runs once a day and needs no broker. Safe to run
more than once on the same day: `notify()`'s per-recipient `dedupe_key`
means a repeat run sends nothing new.
"""

from __future__ import annotations

import datetime as dt

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from attendance.calendar_rules import local_date
from attendance.models import AppSettings
from notifications.services import notify

from ...models import Event


class Command(BaseCommand):
    help = "Notify the owner and assigned lead of events whose alert date is today."

    def add_arguments(self, parser):
        parser.add_argument("--date", help="Office-local date (YYYY-MM-DD). Defaults to today.")

    def handle(self, *args, **options):
        if options["date"]:
            try:
                day = dt.date.fromisoformat(options["date"])
            except ValueError as exc:
                raise CommandError(f"Invalid --date: {options['date']}") from exc
        else:
            day = local_date(timezone.now(), AppSettings.load())

        events = Event.objects.filter(alert_on=day).select_related("owner", "assigned_lead")
        sent = 0
        for event in events:
            for recipient in {event.owner, event.assigned_lead}:
                if recipient is None:
                    continue
                result = notify(
                    recipient,
                    f"Reminder: today is the alert date for '{event.title}'",
                    url=f"/events/{event.id}",
                    dedupe_key=f"event-alert-{event.id}-{day}-{recipient.id}",
                )
                if result is not None:
                    sent += 1

        self.stdout.write(self.style.SUCCESS(f"{sent} alert notification(s) sent for {day}"))
