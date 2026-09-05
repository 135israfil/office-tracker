"""Helper for writing audit entries (§30).

Kept deliberately small. Views call `record()` with the acting user and a payload of
what actually changed — not the whole object, which would bloat the log and duplicate
data that already lives in the row being audited.
"""

from .models import AuditLog


def record(actor, action, target=None, payload=None, target_type=None, target_id=None):
    """Write one audit entry.

    `target` may be any model instance; its class name and pk are stored. `actor` may be
    None for system-initiated actions such as scheduled jobs.
    """
    if target is not None:
        target_type = target_type or target.__class__.__name__
        target_id = target_id or str(target.pk)

    return AuditLog.objects.create(
        actor=actor if (actor and actor.is_authenticated) else None,
        action=action,
        target_type=target_type or "",
        target_id=target_id or "",
        payload=payload or {},
    )


def diff(before: dict, after: dict) -> dict:
    """Return {field: {"from": x, "to": y}} for changed fields only.

    Logging only what changed keeps the audit trail readable and avoids storing a
    complete copy of every record on every edit.
    """
    changes = {}
    for key, new_value in after.items():
        old_value = before.get(key)
        if old_value != new_value:
            changes[key] = {"from": old_value, "to": new_value}
    return changes
