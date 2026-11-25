"""What this machine calls itself (§12).

Kept apart from the collectors: this is identity, gathered once at registration and on
start-up, not activity. Nothing here reads anything about what the user is doing.
"""

from __future__ import annotations

import platform
import socket
import sys

from .version import __version__

# Windows 11 still reports itself as release "10"; the build number is the only thing
# that tells the two apart, and 22000 is the first Windows 11 build.
WINDOWS_11_MIN_BUILD = 22000


def windows_name(release: str, build: int | None) -> str:
    """Human-readable Windows name from the parts `platform` gives us."""
    if release == "10" and build and build >= WINDOWS_11_MIN_BUILD:
        return "Windows 11"
    if release:
        return f"Windows {release}"
    return "Windows"


def operating_system() -> str:
    system = platform.system()
    if system == "Darwin":
        # platform.release() is the Darwin kernel version ("23.6.0"), meaningless to
        # anyone reading the Computers list — platform.mac_ver() gives the actual
        # product version ("14.6.1") instead, the number a user would recognise from
        # "About This Mac".
        version = platform.mac_ver()[0]
        return f"macOS {version}".strip() if version else "macOS"
    if system != "Windows":
        # Development and CI only — the agent ships for Windows and macOS (D3).
        return f"{system} {platform.release()}".strip()

    build = None
    version_info = getattr(sys, "getwindowsversion", None)
    if version_info is not None:  # pragma: no branch - always present on Windows
        try:
            build = version_info().build
        except Exception:  # pragma: no cover - defensive
            build = None
    return windows_name(platform.release(), build)


def computer_name() -> str:
    """The machine name an admin would recognise in the computer list."""
    name = platform.node() or socket.gethostname()
    return name.strip()


def machine_info() -> dict:
    """The registration payload describing this PC."""
    return {
        "computer_name": computer_name(),
        "operating_system": operating_system(),
        "agent_version": __version__,
    }
