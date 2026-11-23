"""Agent configuration and credential storage (§34 Configuration).

Two stores, deliberately separate:

- **`agent.json` in `%PROGRAMDATA%\\OfficeTracker`** holds everything that is not secret:
  the server URL, this machine's identity, and the intervals the server last told us to
  use. It is world-readable by design — support staff need to be able to look at it.
- **Windows Credential Manager**, via `keyring`, holds the device token and nothing
  else. It is never written to the config file, never logged, and there is no fallback
  to disk: if the credential store is unavailable the agent fails loudly rather than
  quietly leaving a token in a text file.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

KEYRING_SERVICE = "OfficeTracker Agent"
KEYRING_USERNAME = "device-token"

CONFIG_FILENAME = "agent.json"
DATA_DIR_ENV = "OFFICE_AGENT_DATA_DIR"


class ConfigError(Exception):
    """Configuration is unusable and the agent cannot continue."""


class TokenStorageError(Exception):
    """The credential store refused to co-operate.

    Deliberately fatal for a registration attempt: a token we cannot store is a token
    that would have to live somewhere worse.
    """


def data_dir() -> Path:
    """Where agent state lives.

    `%PROGRAMDATA%` rather than `%APPDATA%` because the installer writes here once for
    the machine and the agent runs as whichever user is logged in. Overridable through
    an environment variable so tests and dev runs never touch the real install.
    """
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        return Path(override)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "OfficeTracker"
    base = os.environ.get("PROGRAMDATA") or os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "OfficeTracker"
    # Non-Windows, non-macOS only happens in development and CI.
    return Path.home() / ".office-tracker"


def config_path() -> Path:
    return data_dir() / CONFIG_FILENAME


@dataclass
class AgentConfig:
    """The persisted, non-secret half of the agent's state."""

    server_url: str = ""
    computer_id: int | None = None
    computer_name: str = ""
    employee_name: str = ""

    # Server-driven (§35). These are defaults only: the first heartbeat replaces them
    # with whatever the admin has configured, so changing an interval centrally does not
    # require touching a single PC.
    heartbeat_interval_seconds: int = 60
    idle_threshold_seconds: int = 300
    sync_interval_seconds: int = 60
    enabled: bool = True
    # Off by default (README.txt §31, reversed for this capability on
    # 2026-11-22 — see docs/designs/screenshot-based-activity-tracking.md): a
    # fleet-wide kill switch an admin must deliberately turn on, the same
    # "defaults closed" posture the backend's own setting uses.
    screenshot_capture_enabled: bool = False
    screenshot_interval_seconds: int = 60
    config_version: int = 0

    _path: Path | None = field(default=None, repr=False, compare=False)

    # --- Persistence -------------------------------------------------------

    @classmethod
    def load(cls, path: Path | None = None) -> AgentConfig:
        path = path or config_path()
        if not path.exists():
            return cls(_path=path)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"Could not read {path}: {exc}") from exc

        known = {f.name for f in fields(cls) if not f.name.startswith("_")}
        # Ignore unknown keys rather than crashing: a newer agent writing an extra field
        # must not brick an older one during a staged rollout.
        return cls(**{key: value for key, value in raw.items() if key in known}, _path=path)

    def save(self, path: Path | None = None) -> Path:
        path = path or self._path or config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {key: value for key, value in asdict(self).items() if not key.startswith("_")}
        # Write-then-replace so a power cut mid-write cannot leave a truncated config
        # that the agent would refuse to start from.
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(path)
        self._path = path
        return path

    # --- Server-driven settings -------------------------------------------

    def apply_server_config(self, payload: dict) -> bool:
        """Adopt the config the server returned. Returns True if anything changed."""
        changed = False
        for key in (
            "heartbeat_interval_seconds",
            "idle_threshold_seconds",
            "sync_interval_seconds",
            "enabled",
            "screenshot_capture_enabled",
            "screenshot_interval_seconds",
            "config_version",
        ):
            if key in payload and payload[key] != getattr(self, key):
                setattr(self, key, payload[key])
                changed = True
        for key in ("computer_id", "computer_name", "employee_name"):
            if payload.get(key) and payload[key] != getattr(self, key):
                setattr(self, key, payload[key])
                changed = True
        if changed:
            self.save()
        return changed

    @property
    def is_configured(self) -> bool:
        return bool(self.server_url)


# --- Device token -----------------------------------------------------------


def _keyring():
    try:
        import keyring
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise TokenStorageError("The keyring package is not installed.") from exc
    return keyring


def load_token() -> str | None:
    try:
        return _keyring().get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except TokenStorageError:
        raise
    except Exception as exc:
        raise TokenStorageError(f"Could not read the device token: {exc}") from exc


def store_token(token: str) -> None:
    if not token:
        raise TokenStorageError("Refusing to store an empty device token.")
    try:
        _keyring().set_password(KEYRING_SERVICE, KEYRING_USERNAME, token)
    except TokenStorageError:
        raise
    except Exception as exc:
        # No disk fallback. A token in a plaintext file would survive uninstall, back up
        # into cloud sync, and end up in a support ticket screenshot.
        raise TokenStorageError(f"Could not store the device token securely: {exc}") from exc


def clear_token() -> None:
    # Deleting something that is not there is not an error worth failing an uninstall
    # or a re-enrolment over.
    with contextlib.suppress(Exception):
        _keyring().delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
