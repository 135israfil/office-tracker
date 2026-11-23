"""Removing everything this agent left on a machine (Phase 9, uninstall).

An uninstaller that leaves the local queue behind leaves a SQLite file of somebody's
application and website history on a PC that is supposed to no longer be tracked. §31
makes that a privacy question rather than a tidiness one, so removal is part of the
product and not a note in a runbook.

Two things make this awkward enough to deserve its own module:

- **The device token is not in a file.** It lives in Windows Credential Manager, per
  user. An elevated uninstaller runs as the administrator, whose credential store does
  not contain it, so the installer invokes this in the *original* user's context.
- **Uninstall must not fail.** Every step is best-effort and reported; a locked file or
  an already-empty credential store is not a reason to leave a half-removed install and
  an error dialog. The exit code is 0 unless nothing could be removed at all.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from .config import CONFIG_FILENAME, clear_token, data_dir
from .single_instance import LOCK_FILENAME
from .storage.queue import QUEUE_FILENAME
from .storage.screenshot_queue import QUEUE_FILENAME as SCREENSHOT_QUEUE_FILENAME

log = logging.getLogger("agent.cleanup")

# The installer writes this from [Run] with runasoriginaluser. Removing it is this
# module's job for the same reason: the uninstaller has no equivalent flag.
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "OfficeTrackerAgent"

# Written by the agent itself on first run (there is no installer-driven equivalent
# on macOS in this first pass — see the macOS port plan), so cleanup must remove it
# the same way it removes the Windows Run value.
LAUNCH_AGENT_LABEL = "com.officetracker.agent"


def _launch_agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


def _remove_launch_agent() -> str:
    """Unload and delete the LaunchAgent plist, if we are on macOS and it is there."""
    if sys.platform != "darwin":  # pragma: no cover - macOS-only path
        return "skipped (not macOS)"
    import subprocess

    path = _launch_agent_path()
    if not path.exists():
        return "absent"
    subprocess.run(  # noqa: S603 - fixed arguments, no user input
        ["/bin/launchctl", "unload", str(path)], capture_output=True, text=True, check=False
    )
    try:
        path.unlink()
        return "removed"
    except OSError as exc:
        return f"failed: {exc}"


# A Scheduled Task was tried as a replacement for the Run value, to survive a crash and
# not just a login — and reverted (see OfficeTracker.iss's [Run] section) because a
# process Task Scheduler launches is denied the foreground-activation rights pystray's
# tray menu needs, even with an interactive logon trigger: the menu opens but no click
# reaches a handler. This constant, and _remove_scheduled_task below, stay only so a
# machine that already got that build is left clean rather than with an orphaned task
# pointing at a deleted exe — nothing installed after the revert creates one.
SCHEDULED_TASK_NAME = "OfficeTrackerAgent"

# Named individually rather than removing the directory wholesale. The data directory is
# `%PROGRAMDATA%\OfficeTracker`, and a wildcard delete there would be one packaging
# mistake away from taking something that is not ours.
REMOVABLE_FILES = [
    QUEUE_FILENAME,
    f"{QUEUE_FILENAME}-wal",
    f"{QUEUE_FILENAME}-shm",
    SCREENSHOT_QUEUE_FILENAME,
    f"{SCREENSHOT_QUEUE_FILENAME}-wal",
    f"{SCREENSHOT_QUEUE_FILENAME}-shm",
    CONFIG_FILENAME,
    LOCK_FILENAME,
    "agent.log",
]


def _remove_file(path: Path) -> tuple[bool, str]:
    try:
        if not path.exists():
            return False, "absent"
        path.unlink()
        return True, "removed"
    except OSError as exc:
        return False, f"failed: {exc}"


def _remove_run_key() -> str:
    """Delete the legacy HKCU Run value, if it is there. See RUN_KEY above."""
    if sys.platform != "win32":  # pragma: no cover - Windows-only path
        return "skipped (not Windows)"
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, RUN_VALUE)
        return "removed"
    except FileNotFoundError:
        return "absent"
    except OSError as exc:
        return f"failed: {exc}"


def _remove_scheduled_task() -> str:
    """Delete the Scheduled Task, if we are on Windows and it is there."""
    if sys.platform != "win32":  # pragma: no cover - Windows-only path
        return "skipped (not Windows)"
    import subprocess

    # Absolute path rather than relying on PATH resolution: this runs during an
    # uninstall, where the calling context is whatever the uninstaller happened to set
    # up, not a guarantee that System32 is on it.
    schtasks = os.path.join(os.environ.get("SYSTEMROOT", r"C:\Windows"), "System32", "schtasks.exe")
    result = subprocess.run(  # noqa: S603 - fixed arguments, no user input
        [schtasks, "/Delete", "/TN", SCHEDULED_TASK_NAME, "/F"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return "removed"
    # schtasks has no distinct "not found" exit code; it always returns 1 on failure and
    # puts the reason in stderr, so the absent case is told apart by its message.
    if "cannot find" in result.stderr.lower():
        return "absent"
    return f"failed: {result.stderr.strip() or result.returncode}"


def _remove_autostart() -> str:
    """Remove both autostart mechanisms this agent has ever used.

    Every machine has the Run value; a small number, installed during the brief window
    before the Scheduled Task approach was reverted, have the task instead (or as well).
    Running both removals unconditionally means an uninstall is correct either way,
    without needing to know which one put the machine here.
    """
    if sys.platform == "darwin":
        return _remove_launch_agent()

    task_result = _remove_scheduled_task()
    run_key_result = _remove_run_key()
    if task_result == "removed" or run_key_result == "removed":
        return "removed"
    if task_result == "absent" and run_key_result == "absent":
        return "absent"
    return f"scheduled task: {task_result}; run key: {run_key_result}"


def cleanup(*, dry_run: bool = False, directory: Path | None = None) -> dict:
    """Remove local agent state. Returns what happened to each item."""
    base = Path(directory) if directory else data_dir()
    actions: dict[str, str] = {}
    removed = 0

    for name in REMOVABLE_FILES:
        path = base / name
        if dry_run:
            actions[name] = "would remove" if path.exists() else "absent"
            continue
        ok, outcome = _remove_file(path)
        actions[name] = outcome
        removed += int(ok)

    # Autostart, so the agent does not come back at the next login pointing at a binary
    # that is no longer there.
    if dry_run:
        actions["autostart"] = "would remove"
    else:
        actions["autostart"] = _remove_autostart()

    # The token last: while it exists the machine could in principle still report, and
    # if an earlier step raised we would rather have stopped before revoking identity.
    if dry_run:
        actions["device_token"] = "would remove"  # noqa: S105 - a status label, not a secret
    else:
        # `clear_token` already swallows a missing entry, which is the normal case on a
        # PC that was never enrolled.
        clear_token()
        actions["device_token"] = "cleared"  # noqa: S105 - a status label, not a secret
        removed += 1

    # The directory goes only if we emptied it. Anything left is not ours.
    if not dry_run:
        try:
            if base.exists() and not any(base.iterdir()):
                base.rmdir()
                actions["data_directory"] = "removed"
            elif base.exists():
                actions["data_directory"] = "kept (not empty)"
        except OSError as exc:
            actions["data_directory"] = f"kept: {exc}"

    log.info("uninstall cleanup: %s", actions)
    return {"directory": str(base), "actions": actions, "removed": removed, "dry_run": dry_run}
