"""Create ABSENT rows for working days with no attendance (A4).

Run nightly from cron or Task Scheduler:

    python manage.py mark_absentees                # yesterday
    python manage.py mark_absentees --date 2026-08-18
    python manage.py mark_absentees --days 7       # backfill the last 7 days
    python manage.py mark_absentees --dry-run

Deliberately a management command rather than a Celery task: it runs once a day and
needs no broker, and §32 lists Celery as optional.
"""

import datetime as dt

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from attendance.calendar_rules import local_date
from attendance.models import AppSettings
from attendance.services import mark_absentees


class Command(BaseCommand):
    help = "Mark active employees absent on working days with no attendance record."

    def add_arguments(self, parser):
        parser.add_argument("--date", help="Office-local date (YYYY-MM-DD). Defaults to yesterday.")
        parser.add_argument(
            "--days", type=int, default=1, help="Number of days back to process, ending at --date."
        )
        parser.add_argument("--dry-run", action="store_true", help="Report without writing.")

    def handle(self, *args, **options):
        settings_obj = AppSettings.load()
        today = local_date(timezone.now(), settings_obj)

        if options["date"]:
            try:
                end = dt.date.fromisoformat(options["date"])
            except ValueError as exc:
                raise CommandError(f"Invalid --date: {options['date']}") from exc
        else:
            end = today - dt.timedelta(days=1)

        if end >= today:
            # Marking today absent would flag everyone who has not arrived yet.
            raise CommandError("Refusing to process today or a future date.")

        days = max(1, options["days"])
        total = 0
        for offset in range(days):
            day = end - dt.timedelta(days=offset)
            result = mark_absentees(day, dry_run=options["dry_run"])
            if result["skipped"]:
                self.stdout.write(f"{day}: skipped ({result['skipped']})")
            else:
                total += result["created"]
                self.stdout.write(f"{day}: {result['created']} marked absent")

        prefix = "[dry run] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(f"{prefix}{total} absence record(s) across {days} day(s)")
        )
