"""macOS autostart via a per-user LaunchAgent.

Windows gets this for free from the installer, which writes an HKCU\\Run value once at
install time, pointing at a fixed Program Files path (see OfficeTracker.iss). There is no
macOS installer in this first pass — just a .dmg a user drags into /Applications or
anywhere else — so nothing ever wrote the LaunchAgent plist `cleanup.py` has known how to
remove since the macOS port. This module is that missing other half: the agent installs
its own LaunchAgent the first time it actually runs (not on --status/--enroll/
--uninstall-cleanup, which exit before touching this), pointing at wherever it is
actually running from, and repairs it if that path ever changes (the .app was moved, or a
newer version was dropped in over an old plist pointing at a deleted bundle id path).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

# Matches installer/agent.spec's bundle_identifier and cleanup.py's LAUNCH_AGENT_LABEL —
# the same plist both modules must agree on, written here, removed there.
LAUNCH_AGENT_LABEL = "com.officetracker.agent"


def launch_agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


def _executable_path() -> str | None:
    """The actual running binary, or None when this is a plain `python -m agent` dev/test
    run — writing an autostart entry that points at a bare interpreter would silently
    break at the next login rather than relaunch the agent."""
    if not getattr(sys, "frozen", False):
        return None
    return sys.executable


def plist_contents(executable: str) -> str:
    """Pure so the XML shape is testable without touching a real filesystem or
    launchd. RunAtLoad (not KeepAlive): the agent manages its own retry/backoff loops
    (see service.py), so launchd's job is only to start it once per login, not to
    resurrect a process that exited on purpose (e.g. SingleInstance refusing a second
    copy)."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "    <key>Label</key>\n"
        f"    <string>{LAUNCH_AGENT_LABEL}</string>\n"
        "    <key>ProgramArguments</key>\n"
        "    <array>\n"
        f"        <string>{executable}</string>\n"
        "    </array>\n"
        "    <key>RunAtLoad</key>\n"
        "    <true/>\n"
        "    <key>ProcessType</key>\n"
        "    <string>Interactive</string>\n"
        "</dict>\n"
        "</plist>\n"
    )


def ensure_installed() -> str:
    """Write (or repair) the LaunchAgent plist so the agent restarts at every login.

    Best-effort and silent on failure, the same contract as every other platform-glue
    call in this agent (see service.py's module docstring): a user who can run the app
    at all can also just reopen it manually, so a write failure here is an
    inconvenience, never a reason to stop a run that is already under way.
    """
    if sys.platform != "darwin":
        return "skipped (not macOS)"

    executable = _executable_path()
    if executable is None:
        return "skipped (not a frozen build)"

    path = launch_agent_path()
    desired = plist_contents(executable)
    try:
        if path.exists() and path.read_text(encoding="utf-8") == desired:
            return "already installed"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(desired, encoding="utf-8")
    except OSError as exc:
        log.warning("Could not write LaunchAgent plist: %s", exc)
        return f"failed: {exc}"

    # Best-effort only: this activates the job for the *current* login session
    # immediately rather than leaving it to take effect at the next one. A machine
    # where launchctl itself is unreachable still has a correctly-written plist that
    # will work from the next login onward.
    import subprocess

    subprocess.run(  # noqa: S603 - fixed arguments, no user input
        ["/bin/launchctl", "load", "-w", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    return "installed"
