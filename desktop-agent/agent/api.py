"""HTTP client for the agent endpoints (§28, §29).

Every call is short, idempotent-safe and heavily timed out. The agent runs unattended on
someone's desk: a request that hangs is worse than a request that fails, because a
failure retries and a hang stops the heartbeat loop dead.
"""

from __future__ import annotations

import contextlib
import logging

import requests

from .version import __version__

log = logging.getLogger(__name__)

# Connect and read timeouts. A heartbeat that has not completed in ten seconds is not
# going to, and the next one is only a minute away.
TIMEOUT = (5, 10)

# Sync carries up to a hundred sessions and may hit a busy server, so it gets a longer
# read timeout than a heartbeat — but still a bounded one.
SYNC_TIMEOUT = (5, 30)

# A screenshot is a much larger single payload than a session batch; the read timeout
# gives a slow upload link room without being unbounded.
SCREENSHOT_TIMEOUT = (5, 30)

# Backoff bounds for the caller's retry loop. Capped at five minutes so a server that
# comes back after an outage is picked up promptly rather than an hour later.
BACKOFF_BASE_SECONDS = 5
BACKOFF_CAP_SECONDS = 300


class AgentApiError(Exception):
    """A request failed. `status` is None for transport-level failures."""

    def __init__(self, message, status=None, payload=None):
        super().__init__(message)
        self.status = status
        self.payload = payload or {}

    @property
    def is_auth_failure(self) -> bool:
        """401/403 mean this credential will never work again without re-enrolment."""
        return self.status in (401, 403)


def backoff_seconds(attempt: int, base: int = BACKOFF_BASE_SECONDS, cap: int = BACKOFF_CAP_SECONDS):
    """Exponential backoff, clamped. Pure so the schedule can be asserted in tests."""
    if attempt < 0:
        raise ValueError("attempt must not be negative")
    return min(cap, base * (2**attempt))


def normalise_server_url(url: str) -> str:
    """Accept what an admin will actually type.

    `https://office.example.com`, a trailing slash, or the API root pasted in whole all
    have to end up at the same place; getting this wrong produces a 404 that looks like
    a server outage.
    """
    url = (url or "").strip().rstrip("/")
    if not url:
        raise ValueError("A server URL is required.")
    if url.endswith("/api"):
        url = url[: -len("/api")]
    if not url.startswith(("http://", "https://")):
        # Plain hostnames default to HTTPS: §29 requires it, and silently downgrading
        # to HTTP would put a device token on the wire in the clear.
        url = f"https://{url}"
    return url


class AgentClient:
    """Thin wrapper over the four agent endpoints. Stateless apart from the token."""

    def __init__(self, server_url: str, token: str | None = None, session=None, timeout=TIMEOUT):
        # Empty is allowed here specifically so a freshly installed, never-configured
        # machine can still construct an AgentService and show its tray — every request
        # this makes fails with a clear AgentApiError instead (see _url below), which the
        # heartbeat/sync loops already know how to back off from. Anything non-empty must
        # still be a real URL.
        self.server_url = normalise_server_url(server_url) if server_url else ""
        self.token = token
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": f"OfficeTrackerAgent/{__version__}"})

    # --- Plumbing ----------------------------------------------------------

    def _url(self, path: str) -> str:
        if not self.server_url:
            raise AgentApiError("No server URL configured.")
        return f"{self.server_url}/api/agent/{path.strip('/')}/"

    def _request(self, method: str, path: str, *, json_body=None, authenticated=True, timeout=None):
        headers = {}
        if authenticated:
            if not self.token:
                raise AgentApiError("This device is not registered.", status=401)
            headers["Authorization"] = f"Device {self.token}"

        try:
            response = self.session.request(
                method,
                self._url(path),
                json=json_body,
                headers=headers,
                timeout=timeout or self.timeout,
            )
        except requests.RequestException as exc:
            # No status: the request never reached an application. Callers treat this as
            # "retry later", not "give up".
            raise AgentApiError(f"{method} {path} failed: {exc}") from exc

        if response.status_code >= 400:
            payload = {}
            with contextlib.suppress(ValueError):
                payload = response.json()
            detail = payload.get("detail") if isinstance(payload, dict) else None
            raise AgentApiError(
                detail or f"{method} {path} returned {response.status_code}",
                status=response.status_code,
                payload=payload if isinstance(payload, dict) else {},
            )

        if response.status_code == 204 or not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise AgentApiError(f"{method} {path} returned a non-JSON body") from exc

    # --- Endpoints ---------------------------------------------------------

    def register(self, enrollment_code: str, machine: dict) -> dict:
        """Exchange the enrollment code for a device token, which is returned once."""
        body = {"enrollment_code": enrollment_code, **machine}
        result = self._request("POST", "register", json_body=body, authenticated=False)
        self.token = result.get("device_token")
        return result

    def heartbeat(self, state: str = "ONLINE", event: str | None = None, timeout=None) -> dict:
        body = {"state": state, "agent_version": __version__}
        if event:
            body["event"] = event
        return self._request("POST", "heartbeat", json_body=body, timeout=timeout)

    def sync(self, sessions: list[dict]) -> dict:
        """Upload a batch of closed sessions.

        Safe to repeat: the server upserts on `client_event_id`, so a batch sent again
        after a dropped response stores nothing twice.
        """
        return self._request("POST", "sync", json_body={"sessions": sessions}, timeout=SYNC_TIMEOUT)

    def get_config(self) -> dict:
        return self._request("GET", "config")

    def upload_screenshot(self, image: bytes, captured_at: str) -> dict:
        """Upload one captured screenshot.

        Not routed through `_request`: that method only knows how to send a
        JSON body, and this is multipart/form-data carrying a binary image —
        a different enough shape that a parallel, small method is clearer
        than bending `_request` to cover both.
        """
        if not self.token:
            raise AgentApiError("This device is not registered.", status=401)

        try:
            response = self.session.post(
                self._url("screenshot"),
                data={"captured_at": captured_at},
                files={"file": ("screenshot.png", image, "image/png")},
                headers={"Authorization": f"Device {self.token}"},
                timeout=SCREENSHOT_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise AgentApiError(f"POST screenshot failed: {exc}") from exc

        if response.status_code >= 400:
            payload = {}
            with contextlib.suppress(ValueError):
                payload = response.json()
            detail = payload.get("detail") if isinstance(payload, dict) else None
            raise AgentApiError(
                detail or f"POST screenshot returned {response.status_code}",
                status=response.status_code,
                payload=payload if isinstance(payload, dict) else {},
            )
        return {}
