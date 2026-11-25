"""Mark silent machines OFFLINE and close the sessions they left open (§13).

Run every minute from cron or Task Scheduler:

    python manage.py mark_offline_computers
    python manage.py mark_offline_computers --dry-run

A crash or power cut never sends a shutdown event, so this job is what turns "stopped
answering" into "was off". The admin computer list runs the same sweep when it loads, so
this command is the backstop that keeps the data correct even when nobody is looking at
the screen — the reason it exists at all is that an open PC_ON session left dangling
overnight would report the machine as having been on for fifteen hours.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from attendance.models import AppSettings
from computers.models import Computer, ComputerStatus, DeviceType
from computers.services import _stale_filter, offline_after, sweep_offline_computers


class Command(BaseCommand):
    help = "Mark computers offline when heartbeats stop, closing their open PC sessions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Report what would change, write nothing."
        )

    def handle(self, *args, **options):
        settings_obj = AppSettings.load()
        now = timezone.now()

        if options["dry_run"]:
            stale = Computer.objects.filter(
                status__in=[ComputerStatus.ONLINE, ComputerStatus.IDLE]
            ).filter(_stale_filter(now, settings_obj))
            for computer in stale:
                self.stdout.write(f"{computer.computer_name}: last seen {computer.last_seen_at}")
            pc_window = offline_after(settings_obj, DeviceType.PC)
            android_window = offline_after(settings_obj, DeviceType.ANDROID)
            self.stdout.write(
                self.style.SUCCESS(
                    f"[dry run] {stale.count()} computer(s) past their cutoff "
                    f"(PC {pc_window}, Android {android_window})"
                )
            )
            return

        result = sweep_offline_computers(settings_obj=settings_obj)
        self.stdout.write(
            self.style.SUCCESS(
                f"{result['marked_offline']} computer(s) marked offline, "
                f"{result['sessions_closed']} session(s) closed (cutoff {result['cutoff']})"
            )
        )
