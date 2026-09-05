"""Foreground application detection (§15, §34 Application Collector).

`GetForegroundWindow` → `GetWindowThreadProcessId` → `psutil` gives the process behind
whatever window has focus. Three things about this module are deliberate:

- **The window title is read but never returned.** The Phase 1 spike surfaced titles such
  as `PLAN.md - Visual Studio Code`: document and file names, which is file-activity
  monitoring under §31. The title exists here only as a cheap change signal — a title
  read costs 0.001ms against 46ms for the UI Automation read Phase 6 needs — and is
  discarded in the same function that reads it.
- **`process.exe()` may be denied** for elevated processes. §15 asks for the executable
  "where available", so a denial degrades to a name-only sample instead of an error.
- **A friendly application name is preferred** over `chrome.exe`, because §15's example
  output is "Google Chrome". It comes from the executable's own version resource, and
  falls back to the process name when that is unavailable.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass

log = logging.getLogger(__name__)

# Windows shell processes that own the desktop, the lock screen and the task switcher.
# They are not applications anyone "used", and recording them turns every Alt-Tab into a
# session.
SHELL_PROCESSES = {
    "explorer.exe",
    "searchhost.exe",
    "searchapp.exe",
    "startmenuexperiencehost.exe",
    "shellexperiencehost.exe",
    "lockapp.exe",
    "textinputhost.exe",
    "applicationframehost.exe",
}


@dataclass(frozen=True)
class ForegroundApp:
    """What the sampler learns about the focused window.

    `title_signature` is a change signal only. It is never stored, never logged and
    never sent — see the module docstring.
    """

    application_name: str
    executable_name: str
    title_signature: str = ""

    @property
    def is_empty(self) -> bool:
        return not self.application_name


EMPTY = ForegroundApp(application_name="", executable_name="")


def friendly_name(file_description: str | None, process_name: str) -> str:
    """Prefer the executable's own description, fall back to its filename.

    Pure so the fallback chain is testable: `Code.exe` with a description becomes
    "Visual Studio Code", and without one stays "Code".
    """
    description = (file_description or "").strip()
    if description:
        return description[:200]
    name = (process_name or "").strip()
    if name.lower().endswith(".exe"):
        name = name[: -len(".exe")]
    return name[:200]


def is_shell_process(process_name: str) -> bool:
    return (process_name or "").lower() in SHELL_PROCESSES


def _file_description(exe_path):  # pragma: no cover - requires a real executable
    """Read FileDescription out of an executable's version resource."""
    if not exe_path:
        return None
    try:
        import win32api

        info = win32api.GetFileVersionInfo(exe_path, "\\VarFileInfo\\Translation")
        language, codepage = info[0]
        key = f"\\StringFileInfo\\{language:04x}{codepage:04x}\\FileDescription"
        return win32api.GetFileVersionInfo(exe_path, key)
    except Exception:
        # Plenty of executables ship no version resource. That is not an error, it just
        # means the process name is the best name available.
        return None


def foreground_app() -> ForegroundApp:  # pragma: no cover - requires a Windows desktop
    """The focused application, or EMPTY when there is nothing to attribute time to."""
    if sys.platform != "win32":
        return EMPTY

    try:
        import psutil
        import win32gui
        import win32process
    except ImportError as exc:
        log.error("Application collector unavailable: %s", exc)
        return EMPTY

    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            # Normal on the lock screen and during desktop switches.
            return EMPTY

        # Read, hash, discard. The raw title must not outlive this function.
        title_signature = str(hash(win32gui.GetWindowText(hwnd)))

        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid)
        process_name = process.name()
        if is_shell_process(process_name):
            return EMPTY

        try:
            exe_path = process.exe()
        except (psutil.AccessDenied, PermissionError):
            exe_path = None

        return ForegroundApp(
            application_name=friendly_name(_file_description(exe_path), process_name),
            executable_name=process_name,
            title_signature=title_signature,
        )
    except Exception as exc:
        # A process that exits between the handle and the lookup is routine. One lost
        # sample is invisible; a crashed sampler is not.
        log.debug("Foreground app unavailable: %s", exc)
        return EMPTY
