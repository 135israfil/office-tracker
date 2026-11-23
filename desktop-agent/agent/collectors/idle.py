"""Idle detection (§14, §34 Activity Collector).

`GetLastInputInfo` returns the tick count of the last keyboard or mouse input. It says
*when* input last happened and nothing whatsoever about what was typed — which is what
makes it the right primitive under §31. No hook is installed, nothing is intercepted.

The Phase 1 spike found the trap: `GetTickCount` wraps every ~49.7 days, so a naive
subtraction on a long-uptime machine yields a huge negative number and the agent decides
everyone has been idle since 1970. The masking below is that fix.
"""

from __future__ import annotations

import ctypes
import logging
import sys

log = logging.getLogger(__name__)

# Tick counters are 32-bit milliseconds.
TICK_WRAP = 0xFFFFFFFF

# The two states the heartbeat reports. Named for the API's vocabulary, not the OS's.
STATE_ONLINE = "ONLINE"
STATE_IDLE = "IDLE"


def elapsed_ticks(last_input_tick: int, now_tick: int) -> int:
    """Milliseconds between two tick counts, correct across a 32-bit wrap."""
    return (now_tick - last_input_tick) & TICK_WRAP


def heartbeat_state(idle_seconds_value: float, threshold_seconds: int) -> str:
    """Map measured idleness onto what the heartbeat reports.

    The threshold comes from the server (§35), never from a constant here, so an admin
    changing it takes effect on the next config poll rather than the next release.
    """
    return STATE_IDLE if idle_seconds_value >= threshold_seconds else STATE_ONLINE


class _LastInputInfo(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def _idle_seconds_macos() -> float:  # pragma: no cover - requires a real macOS session
    try:
        import Quartz
    except ImportError as exc:
        log.error("Idle collector unavailable: %s", exc)
        return 0.0

    try:
        return Quartz.CGEventSourceSecondsSinceLastEventType(
            Quartz.kCGEventSourceStateCombinedSessionState, Quartz.kCGAnyInputEventType
        )
    except Exception:
        # Same honest-zero convention as the Windows GetLastInputInfo failure below.
        log.debug("CGEventSourceSecondsSinceLastEventType failed", exc_info=True)
        return 0.0


def idle_seconds() -> float:
    """Seconds since the last keyboard or mouse input on this session.

    Returns 0.0 off Windows and macOS, which is the honest answer for a platform the
    agent does not support: it keeps development and CI runnable without pretending to
    measure.
    """
    if sys.platform == "darwin":
        return _idle_seconds_macos()
    if sys.platform != "win32":
        return 0.0

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    info = _LastInputInfo()
    info.cbSize = ctypes.sizeof(info)
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        # A locked workstation or a session change can make this fail transiently. The
        # spike showed it recovers; reporting "not idle" for one beat is the safe answer
        # because it never invents idle time that did not happen.
        return 0.0

    return elapsed_ticks(info.dwTime, kernel32.GetTickCount()) / 1000.0
