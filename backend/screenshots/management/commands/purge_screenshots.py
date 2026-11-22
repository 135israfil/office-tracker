"""Delete captured screenshots past the retention window.

python manage.py purge_screenshots --dry-run     # report what would go
python manage.py purge_screenshots               # delete it
python manage.py purge_screenshots --days 3       # override the configured window once
"""

from django.core.management.base import BaseCommand, CommandError

from attendance.models import AppSettings
from screenshots.retention import MINIMUM_RETENTION_DAYS, purge_screenshots


class Command(BaseCommand):
    help = "Delete screenshot captures older than the configured retention window."

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
            settings_obj.screenshot_retention_days = days

        result = purge_screenshots(
            dry_run=options["dry_run"], settings_obj=settings_obj, actor=None
        )

        prefix = "[dry run] " if result["dry_run"] else ""
        verb = "would delete" if result["dry_run"] else "deleted"
        self.stdout.write(
            f"{prefix}retention {result['retention_days']} days, "
            f"cutoff {result['cutoff'].isoformat()}"
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}{verb} {result['eligible' if result['dry_run'] else 'deleted']} "
                "screenshot(s)"
            )
        )
