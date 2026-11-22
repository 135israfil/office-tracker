"""Registration, liveness and PC-session rules (§12, §13).

All of it lives here rather than in views so the API, the admin actions and the nightly
sweep share one implementation. The rule that matters most in this module:

    A crash, a power cut or a yanked network cable never sends a shutdown event.

So "the PC is off" can never be something the server waits to be told. It is inferred
from missed heartbeats, and the open PC_ON session is closed at the *last heartbeat*,
not at the moment the sweep happens to notice — otherwise a machine that died at 18:05
and was noticed at 09:00 the next morning would report fifteen hours of uptime.
"""

from __future__ import annotations

import datetime as dt

from django.db import transaction
from django.utils import timezone

from activities.models import Activity, ActivityType
from attendance.models import AppSettings

from .models import CLOSING_EVENTS, Computer, ComputerStatus, LifecycleEvent, normalise_code

# How many missed heartbeats before a machine counts as gone. Three is the smallest
# number that tolerates one dropped request plus one slow one without flapping.
MISSED_HEARTBEATS_BEFORE_OFFLINE = 3


class RegistrationError(Exception):
    """Enrolment refused. Surfaces as a 400 with the message shown to the installer."""


def offline_after(settings_obj=None) -> dt.timedelta:
    settings_obj = settings_obj or AppSettings.load()
    return dt.timedelta(
        seconds=settings_obj.heartbeat_interval_seconds * MISSED_HEARTBEATS_BEFORE_OFFLINE
    )


def agent_config_payload(settings_obj=None, computer: Computer | None = None) -> dict:
    """What `GET /api/agent/config/` and every heartbeat response carry.

    `config_version` lets the agent notice a change without diffing: it is the settings
    row's last-modified time in milliseconds, which moves whenever an admin saves the
    settings screen. Milliseconds rather than seconds because two saves inside the same
    second are perfectly possible and would otherwise look like no change at all.
    """
    settings_obj = settings_obj or AppSettings.load()
    payload = {
        "idle_threshold_seconds": settings_obj.idle_threshold_seconds,
        "heartbeat_interval_seconds": settings_obj.heartbeat_interval_seconds,
        "sync_interval_seconds": settings_obj.sync_interval_seconds,
        "enabled": settings_obj.agent_enabled,
        "screenshot_capture_enabled": settings_obj.screenshot_capture_enabled,
        "screenshot_interval_seconds": settings_obj.screenshot_interval_seconds,
        "config_version": int(settings_obj.updated_at.timestamp() * 1000),
    }
    if computer is not None:
        payload["computer_id"] = computer.id
        payload["computer_name"] = computer.computer_name
        payload["employee_name"] = computer.employee.name
    return payload


# --- Registration -----------------------------------------------------------


@transaction.atomic
def register_device(
    *,
    enrollment_code: str,
    computer_name: str = "",
    operating_system: str = "",
    agent_version: str = "",
) -> tuple[Computer, str]:
    """Exchange a one-time enrollment code for a device token.

    The row is locked for the duration so two agents racing on the same code cannot both
    walk away with a token.
    """
    code = normalise_code(enrollment_code)
    if not code:
        raise RegistrationError("An enrollment code is required.")

    computer = (
        Computer.objects.select_for_update()
        .select_related("employee")
        .filter(enrollment_code=code)
        .first()
    )
    if computer is None:
        # Same message for "never existed" and "already used": a caller probing codes
        # learns nothing from the difference.
        raise RegistrationError("Unknown or already-used enrollment code.")
    if computer.status == ComputerStatus.DISABLED:
        raise RegistrationError("This computer has been disabled by an administrator.")
    if not computer.enrollment_valid:
        raise RegistrationError("This enrollment code has expired. Ask for a new one.")

    token = computer.issue_device_token()
    if computer_name:
        computer.computer_name = computer_name
    computer.operating_system = operating_system or computer.operating_system
    computer.agent_version = agent_version or computer.agent_version
    # Registered but not yet heard from: the first heartbeat is what makes it online.
    computer.status = ComputerStatus.OFFLINE
    computer.save()
    return computer, token


# --- PC_ON sessions ---------------------------------------------------------


def open_session(computer: Computer, at) -> Activity:
    return Activity.objects.create(
        employee=computer.employee,
        computer=computer,
        activity_type=ActivityType.PC_ON,
        start_time=at,
    )


def current_session(computer: Computer) -> Activity | None:
    return (
        Activity.objects.filter(
            computer=computer, activity_type=ActivityType.PC_ON, end_time__isnull=True
        )
        .order_by("-start_time")
        .first()
    )


def close_session(computer: Computer, at, *, by_server: bool = False) -> Activity | None:
    session = current_session(computer)
    if session is None:
        return None
    return session.close(at, by_server=by_server)


# --- Heartbeat --------------------------------------------------------------


@transaction.atomic
def record_heartbeat(
    computer: Computer,
    *,
    state: str = ComputerStatus.ONLINE,
    event: str | None = None,
    agent_version: str = "",
    now=None,
) -> dict:
    """Apply one heartbeat and return the config the agent should adopt.

    `state` is the agent's own view (ACTIVE / IDLE); `event` is an optional lifecycle
    transition riding along with it. Liveness is always stamped with *server* time: a PC
    with a wrong clock must not be able to appear online in the future or the past.
    """
    now = now or timezone.now()
    previous_seen = computer.last_seen_at

    if event:
        event = event.upper()
        if event not in LifecycleEvent.values:
            raise ValueError(f"Unknown lifecycle event: {event}")

    session = current_session(computer)

    if event == LifecycleEvent.STARTUP and session is not None:
        # The machine says it just booted while we still hold an open session, so the
        # previous run ended without telling us. Close the old session at the last sign
        # of life rather than now, then start a fresh one.
        session.close(previous_seen or session.start_time, by_server=True)
        session = None

    if event in CLOSING_EVENTS:
        if session is not None:
            session.close(now)
        status = ComputerStatus.OFFLINE
    else:
        if session is None:
            # First heartbeat, or the first one after an inferred shutdown. Either way
            # the PC is on now, so the session starts now.
            open_session(computer, now)
        status = ComputerStatus.IDLE if state == ComputerStatus.IDLE else ComputerStatus.ONLINE

    computer.last_seen_at = now
    computer.status = status
    if agent_version:
        computer.agent_version = agent_version
    computer.save(update_fields=["last_seen_at", "status", "agent_version", "updated_at"])

    return agent_config_payload(computer=computer)


# --- Offline sweep ----------------------------------------------------------


def sweep_offline_computers(now=None, *, settings_obj=None) -> dict:
    """Mark silent machines OFFLINE and close the sessions they left open.

    Idempotent and cheap — it touches only rows that are both non-OFFLINE and stale — so
    it is safe to call from the admin list view as well as from cron. Cron is the
    backstop; the list-view call is what stops a dashboard claiming a machine is online
    twenty minutes after it died.
    """
    settings_obj = settings_obj or AppSettings.load()
    now = now or timezone.now()
    cutoff = now - offline_after(settings_obj)

    # A registered machine that has never checked in is already OFFLINE and is not
    # "stale" — there is nothing to close and nothing to change.
    stale = list(
        Computer.objects.filter(
            status__in=[ComputerStatus.ONLINE, ComputerStatus.IDLE],
            last_seen_at__lt=cutoff,
        )
    )

    closed = 0
    for computer in stale:
        with transaction.atomic():
            session = current_session(computer)
            if session is not None:
                session.close(computer.last_seen_at or session.start_time, by_server=True)
                closed += 1
            computer.status = ComputerStatus.OFFLINE
            computer.save(update_fields=["status", "updated_at"])

    return {"marked_offline": len(stale), "sessions_closed": closed, "cutoff": cutoff}
