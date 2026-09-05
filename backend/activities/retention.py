"""Deleting raw activity past its retention window (D5, §31).

§31 requires a data-retention policy; D5 makes the window an admin setting rather than a
constant. This module is the half that actually destroys data, so it is written to be
answerable afterwards:

- **It deletes activity and nothing else.** Attendance, punches and leave are business
  records, not surveillance data, and A6 says they are never auto-deleted. The queryset
  here names `Activity` and no other model, so there is no path by which a bug widens it.
- **Every run is auditable.** A delete job nobody can reconstruct is a liability, so the
  count, the cutoff and the window used are written to the audit log — including runs
  that deleted nothing, because "the job ran and found nothing" and "the job did not run"
  are different facts.
- **Dry run is real.** It counts through exactly the same queryset the deleting path
  uses, so what it reports is what would go.

The cutoff is an office-local day boundary, not "now minus N×24h". With a 90-day window
the rule people expect is "we keep the last 90 days", and a run at 02:00 should not
delete four hours more than a run at 22:00 did.
"""

from __future__ import annotations

import datetime as dt
import logging

from django.utils import timezone

from attendance.calendar_rules import local_date
from attendance.models import AppSettings

from .models import Activity
from .queries import day_window

logger = logging.getLogger(__name__)

# Rows are deleted in batches. One `DELETE ... WHERE start_time < cutoff` over a year of
# a fifty-PC fleet is a single long transaction holding locks the agent sync also wants;
# batching keeps each transaction short and the job interruptible without losing the
# work already done.
BATCH_SIZE = 5_000

# A floor under the admin-configurable window. `AppSettings` already validates a minimum,
# but this job is the thing that does the deleting and it does not delegate its own
# safety: a settings row written before that validator existed, or edited directly in the
# database, must not be able to wipe everything.
MINIMUM_RETENTION_DAYS = 7


def retention_cutoff(settings_obj=None, now=None) -> tuple[dt.datetime, int]:
    """The instant before which activity may be deleted, and the window it came from.

    Returns the *start* of the office-local day that is `retention_days` before today,
    so the window is a whole number of calendar days rather than a rolling instant.
    """
    settings_obj = settings_obj or AppSettings.load()
    now = now or timezone.now()

    days = max(MINIMUM_RETENTION_DAYS, int(settings_obj.activity_retention_days))
    today = local_date(now, settings_obj)
    oldest_kept_day = today - dt.timedelta(days=days)
    cutoff, _ = day_window(oldest_kept_day, settings_obj)
    return cutoff, days


def expired_activity(cutoff: dt.datetime):
    """The rows eligible for deletion.

    A session is judged by when it **ended**, not when it started: one that began before
    the cutoff but ran past it is partly inside the window people were promised, and
    deleting it would silently shorten their history. Sessions still open have not ended
    at all and are never eligible.
    """
    return Activity.objects.filter(end_time__isnull=False, end_time__lt=cutoff)


def purge_activity(*, dry_run: bool = False, actor=None, settings_obj=None, now=None) -> dict:
    """Delete activity older than the configured window. Returns what it did."""
    settings_obj = settings_obj or AppSettings.load()
    cutoff, days = retention_cutoff(settings_obj, now)
    queryset = expired_activity(cutoff)

    eligible = queryset.count()
    deleted = 0

    if not dry_run and eligible:
        while True:
            # Delete by primary key rather than by re-running the date filter, so a
            # session closed by an agent mid-run cannot be swept into a batch that was
            # sized before it existed.
            batch = list(queryset.values_list("pk", flat=True)[:BATCH_SIZE])
            if not batch:
                break
            removed, _ = Activity.objects.filter(pk__in=batch).delete()
            deleted += removed
            if len(batch) < BATCH_SIZE:
                break

    result = {
        "retention_days": days,
        "cutoff": cutoff,
        "eligible": eligible,
        "deleted": deleted,
        "dry_run": dry_run,
    }

    logger.info(
        "activity retention: window=%sd cutoff=%s eligible=%s deleted=%s%s",
        days,
        cutoff.isoformat(),
        eligible,
        deleted,
        " (dry run)" if dry_run else "",
    )

    # Written even when nothing was deleted. The audit trail has to be able to show the
    # job ran, otherwise a silent failure looks exactly like a quiet week.
    from core.audit import record
    from core.models import AuditLog

    record(
        actor,
        AuditLog.Action.ACTIVITY_PURGED,
        target_type="Activity",
        target_id="",
        payload={
            "retention_days": days,
            "cutoff": cutoff.isoformat(),
            "eligible": eligible,
            "deleted": deleted,
            "dry_run": dry_run,
        },
    )

    return result
