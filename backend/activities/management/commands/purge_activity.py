"""Delete raw activity past the retention window (D5, §31).

Run nightly, after the absentee job:

    python manage.py purge_activity --dry-run     # report what would go
    python manage.py purge_activity               # delete it
    python manage.py purge_activity --days 30     # override the configured window once

`--days` is deliberately awkward to reach for: the window belongs in settings, where it
is audited and where the API makes shortening it a confirmed action. The override exists
for a one-off clear-out under supervision, and it refuses to go below the floor the
module enforces.

Attendance, punches and leave are never touched. Only `Activity` rows are deleted.
"""

from django.core.management.base import BaseCommand, CommandError

from activities.retention import MINIMUM_RETENTION_DAYS, purge_activity
from attendance.models import AppSettings


class Command(BaseCommand):
    help = "Delete activity sessions older than the configured retention window."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count what would be deleted, without deleting it.",
        )
        parser.add_argument(
            "--days",
            type=int,
            help="Override the configured retention window for this run only.",
        )

    def handle(self, *args, **options):
        settings_obj = AppSettings.load()

        if options["days"] is not None:
            days = options["days"]
            if days < MINIMUM_RETENTION_DAYS:
                raise CommandError(
                    f"--days {days} is below the {MINIMUM_RETENTION_DAYS}-day minimum."
                )
            # A copy, not a save: an override for one run must not quietly become the
            # configured policy for every run after it.
            settings_obj.activity_retention_days = days

        result = purge_activity(dry_run=options["dry_run"], settings_obj=settings_obj, actor=None)

        prefix = "[dry run] " if result["dry_run"] else ""
        verb = "would delete" if result["dry_run"] else "deleted"
        self.stdout.write(
            f"{prefix}retention {result['retention_days']} days, "
            f"cutoff {result['cutoff'].isoformat()}"
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}{verb} {result['eligible' if result['dry_run'] else 'deleted']} "
                "activity session(s)"
            )
        )
