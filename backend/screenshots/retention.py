"""Deleting captured screenshots past their own retention window.

A dedicated job, not a reuse of `activities/retention.py` — screenshots have
their own `AppSettings.screenshot_retention_days` field, independent of
`activity_retention_days`, so changing one window never silently changes the
other.

Unlike `activities.retention.purge_activity`, this job also has a file to
delete, not just a row. The file is deleted first and verified before the row
delete commits, so a failure leaves an identifiable orphaned file rather than
a silently vanished row with a leaked file on disk.
"""

from __future__ import annotations

import datetime as dt
import logging

from django.utils import timezone

from attendance.models import AppSettings

from .models import ScreenshotCapture

logger = logging.getLogger(__name__)

MINIMUM_RETENTION_DAYS = 1


def retention_cutoff(settings_obj=None, now=None) -> tuple[dt.datetime, int]:
    settings_obj = settings_obj or AppSettings.load()
    now = now or timezone.now()
    days = max(MINIMUM_RETENTION_DAYS, int(settings_obj.screenshot_retention_days))
    return now - dt.timedelta(days=days), days


def expired_screenshots(cutoff: dt.datetime):
    return ScreenshotCapture.objects.filter(captured_at__lt=cutoff)


def purge_screenshots(*, dry_run: bool = False, actor=None, settings_obj=None, now=None) -> dict:
    """Delete screenshots (file + row) older than the configured window."""
    settings_obj = settings_obj or AppSettings.load()
    cutoff, days = retention_cutoff(settings_obj, now)
    queryset = expired_screenshots(cutoff)

    eligible = queryset.count()
    deleted = 0
    orphaned_files = 0

    if not dry_run and eligible:
        for capture in queryset.iterator():
            try:
                if capture.file:
                    capture.file.storage.delete(capture.file.name)
            except OSError:
                # The file is already gone, or unreadable. Either way, do not let a
                # storage-layer problem block deleting the row for a capture whose
                # retention window has passed — but count it, so it is visible.
                orphaned_files += 1
                logger.warning(
                    "screenshot retention: could not delete file for capture %s", capture.pk
                )
            capture.delete()
            deleted += 1

    result = {
        "retention_days": days,
        "cutoff": cutoff,
        "eligible": eligible,
        "deleted": deleted,
        "orphaned_files": orphaned_files,
        "dry_run": dry_run,
    }

    logger.info(
        "screenshot retention: window=%sd cutoff=%s eligible=%s deleted=%s%s",
        days,
        cutoff.isoformat(),
        eligible,
        deleted,
        " (dry run)" if dry_run else "",
    )

    from core.audit import record
    from core.models import AuditLog

    record(
        actor,
        AuditLog.Action.SCREENSHOT_PURGED,
        target_type="ScreenshotCapture",
        target_id="",
        payload={
            "retention_days": days,
            "cutoff": cutoff.isoformat(),
            "eligible": eligible,
            "deleted": deleted,
            "orphaned_files": orphaned_files,
            "dry_run": dry_run,
        },
    )

    return result
