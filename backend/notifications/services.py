"""Helper for creating notifications (mirrors core.audit.record's shape).

Kept deliberately small: callers pass who, what and where, not a whole object.
"""

from __future__ import annotations

from .models import Notification


def notify(recipient, message, url="", dedupe_key=None):
    """Create one notification. `recipient` may be None (a no-op), so callers
    can pass a possibly-unset field (e.g. `event.assigned_lead`) directly
    without a guard. Returns None, without writing, if `dedupe_key` is given
    and already used — the alert-date reminder's safeguard against double-send."""
    if recipient is None:
        return None
    if dedupe_key and Notification.objects.filter(dedupe_key=dedupe_key).exists():
        return None
    return Notification.objects.create(
        recipient=recipient, message=message, url=url, dedupe_key=dedupe_key
    )
