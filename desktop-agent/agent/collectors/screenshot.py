"""Screenshot capture (README.txt §31, reversed for this one capability on
2026-11-22 — see docs/designs/screenshot-based-activity-tracking.md).

Uses `PIL.ImageGrab`, already a dependency of this agent (pystray draws the
tray icon with Pillow) — no new dependency needed. This module does nothing
but grab a bitmap and encode it; it cannot synthesise input, read the
clipboard, or do anything else `scripts/check_privacy.py` still bans.
"""

from __future__ import annotations

import io
import logging
import sys

log = logging.getLogger(__name__)


def capture_screenshot() -> bytes | None:
    """One screenshot, PNG-encoded, or None if it could not be taken.

    Mirrors collectors.idle.idle_seconds' convention: return the honest
    empty answer rather than raise, so a capture failure cannot take the
    screenshot loop down any more than a bad idle reading takes heartbeat
    down.
    """
    if sys.platform != "win32":
        return None

    try:
        from PIL import ImageGrab
    except ImportError:
        log.error("Screenshot collector unavailable: Pillow not installed")
        return None

    try:
        image = ImageGrab.grab()
    except Exception:
        log.exception("Screenshot capture failed")
        return None

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
