"""The agent service: enrolment, heartbeat, sampling and sync (§34).

Everything time- and network-dependent is injected — the clock, the sleep function, the
collectors, the queue, the client — so the whole thing is testable without a network, a
Windows box, or a wait. That is not test theatre: these loops run unattended for weeks,
and their failure modes (a token that stopped working, a server that came back after an
outage, an interval the admin changed at lunchtime, a laptop that slept through a
session) are exactly the ones nobody is watching for.

Four loops, deliberately independent:

- **heartbeat** — liveness and PC-on sessions. Cheap, and the one the server uses to
  decide whether this machine is on at all.
- **sampler** — reads the collectors every couple of seconds and hands changes to the
  session builder. Never touches the network.
- **sync** — drains the local queue to the server. Never touches the collectors.
- **screenshots** — captures and uploads screenshots, when the fleet switch is on
  (README.txt §31, reversed for this one capability — see docs/designs/
  screenshot-based-activity-tracking.md). Off by default; a stuck capture or a slow
  upload must not affect the other three any more than they affect each other.

Keeping them apart means a server outage cannot stop collection, and a stuck collector
cannot stop the machine from reporting that it is alive.
"""

from __future__ import annotations

import datetime as dt
import logging
import threading

from . import config as config_module
from .api import AgentApiError, AgentClient, backoff_seconds
from .collectors.application import foreground_app
from .collectors.browser import BrowserCollector
from .collectors.idle import STATE_ONLINE, heartbeat_state, idle_seconds
from .collectors.screenshot import capture_screenshot
from .machine import machine_info
from .sessions import Sample, SessionBuilder
from .storage.queue import SessionQueue
from .storage.screenshot_queue import ScreenshotQueue
from .sync.client import SyncService
from .version import __version__

log = logging.getLogger(__name__)

# A lifecycle event is worth reporting quickly, but the shutdown path cannot afford to
# wait for a slow server: Windows is already counting down.
EVENT_TIMEOUT = (3, 3)

# Fast enough to attribute a short app switch, slow enough to be invisible in Task
# Manager — the window-title read that gates the expensive work costs ~0.001ms.
SAMPLE_INTERVAL_SECONDS = 2


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class NotRegistered(Exception):
    """No device token. The agent can do nothing useful until it is enrolled."""


class AgentService:
    def __init__(
        self,
        config,
        *,
        client=None,
        idle_reader=idle_seconds,
        app_reader=foreground_app,
        browser_collector=None,
        queue=None,
        builder=None,
        sync_service=None,
        screenshot_queue=None,
        screenshot_reader=capture_screenshot,
        clock=_utcnow,
        sleep=None,
        token_loader=config_module.load_token,
        token_saver=config_module.store_token,
        token_clearer=config_module.clear_token,
    ):
        self.config = config
        self.idle_reader = idle_reader
        self.app_reader = app_reader
        self.browser = browser_collector or BrowserCollector()
        self.screenshot_reader = screenshot_reader
        self.clock = clock
        self.token_loader = token_loader
        self.token_saver = token_saver
        self.token_clearer = token_clearer

        self._stop = threading.Event()
        # Held for the duration of every drain, whether it is run_sync's own periodic
        # call or a manually-requested one (the tray's "Sync now"): two drains in flight
        # at once would each pull from the same pending rows and upload them twice.
        self._sync_lock = threading.Lock()
        # Injected so tests do not really sleep; the default waits on the stop event so
        # a quit request is honoured immediately instead of after a full interval.
        self._sleep = sleep or self._stop.wait

        self.client = client or AgentClient(config.server_url, token=self._safe_token())
        self.builder = builder or SessionBuilder()
        self._queue = queue
        self._sync = sync_service
        self._screenshot_queue = screenshot_queue

        self.last_error: str | None = None
        self.last_state: str | None = None
        self.consecutive_failures = 0

    # --- Lazily-created collaborators --------------------------------------

    @property
    def queue(self) -> SessionQueue:
        """Opened on first use so `--status` and `--enroll` do not create a database
        they never write to."""
        if self._queue is None:
            self._queue = SessionQueue()
        return self._queue

    @property
    def sync_service(self) -> SyncService:
        if self._sync is None:
            self._sync = SyncService(self.queue, self.client)
        return self._sync

    @property
    def screenshot_queue(self) -> ScreenshotQueue:
        """Opened on first use, same reasoning as `queue` above."""
        if self._screenshot_queue is None:
            self._screenshot_queue = ScreenshotQueue()
        return self._screenshot_queue

    # --- Credentials -------------------------------------------------------

    def _safe_token(self):
        try:
            return self.token_loader()
        except config_module.TokenStorageError as exc:
            log.error("Device token unreadable: %s", exc)
            return None

    @property
    def is_registered(self) -> bool:
        return bool(self.client.token)

    def enroll(self, enrollment_code: str) -> dict:
        """Register this PC and store the token that comes back.

        The token is saved before anything else happens: a successful registration whose
        token was lost would need an admin to issue a fresh code, and the old one is
        already spent.
        """
        result = self.client.register(enrollment_code, machine_info())
        token = result.get("device_token")
        if not token:
            raise AgentApiError("Registration succeeded but returned no device token.")

        self.token_saver(token)
        self.client.token = token

        computer = result.get("computer") or {}
        self.config.computer_id = computer.get("id")
        self.config.computer_name = computer.get("computer_name") or self.config.computer_name
        self.config.employee_name = computer.get("employee_name", "")
        self.config.save()
        self.config.apply_server_config(result.get("config") or {})
        log.info("Registered as %s", self.config.computer_name)
        return result

    def forget(self):
        """Drop the credential. Used when the server says it is no longer valid."""
        self.token_clearer()
        self.client.token = None
        self.config.computer_id = None
        self.config.save()

    # --- Heartbeat ---------------------------------------------------------

    def current_state(self) -> str:
        try:
            return heartbeat_state(self.idle_reader(), self.config.idle_threshold_seconds)
        except Exception:
            # Never let a collector failure silence liveness: a PC that is on but cannot
            # measure idleness is still a PC that is on.
            log.exception("Idle measurement failed; reporting active")
            return STATE_ONLINE

    def heartbeat(self, event: str | None = None, timeout=None) -> dict:
        if not self.is_registered:
            raise NotRegistered("This device has not been enrolled yet.")

        state = self.current_state()
        try:
            response = self.client.heartbeat(state=state, event=event, timeout=timeout)
        except AgentApiError as exc:
            self.consecutive_failures += 1
            self.last_error = str(exc)
            if exc.is_auth_failure:
                # The server has revoked this device. Retrying forever would be noise;
                # the machine needs a new enrollment code from an admin.
                log.error("Device credential rejected: %s", exc)
                self.forget()
            raise

        self.consecutive_failures = 0
        self.last_error = None
        self.last_state = state
        self.config.apply_server_config(response.get("config") or {})
        return response

    def report_event(self, event: str) -> bool:
        """Send a lifecycle event now, on a short timeout. Never raises.

        Called from the Windows message pump, including during shutdown, so a failure
        here has to be swallowed: the server infers the same outcome from silence.
        """
        try:
            self.heartbeat(event=event, timeout=EVENT_TIMEOUT)
            return True
        except (AgentApiError, NotRegistered) as exc:
            log.warning("Could not report %s: %s", event, exc)
            return False

    # --- Sampling ----------------------------------------------------------

    @property
    def is_collecting(self) -> bool:
        """Collection needs both an enrolled device and the fleet switch on.

        Sampling before enrolment would buffer activity for a machine the server has
        never heard of, and the fleet switch (§35) exists precisely so an admin can stop
        collection without visiting a desk.
        """
        return self.is_registered and self.config.enabled

    @property
    def is_capturing_screenshots(self) -> bool:
        """Screenshot capture needs both collection generally enabled and its
        own, separate fleet switch on — off by default, so a fleet never
        starts capturing screenshots just because an admin turned on
        ordinary activity collection."""
        return self.is_collecting and self.config.screenshot_capture_enabled

    def sample_once(self) -> list[dict]:
        """Take one reading and queue whatever sessions it closed."""
        now = self.clock()

        if not self.is_collecting:
            # Close what is open rather than leaving it to absorb the pause. Same
            # principle as the sample-gap rule: unobserved time is not usage.
            return self._enqueue(self.builder.flush(now))

        try:
            state = heartbeat_state(self.idle_reader(), self.config.idle_threshold_seconds)
            app = self.app_reader()
            # Only asked when the foreground app is a browser, and only actually read
            # when its window title changed — see BrowserCollector.
            domain = self.browser.domain_for(app) or ""
        except Exception:
            log.exception("Sampling failed; skipping this tick")
            return []

        return self._enqueue(
            self.builder.observe(Sample(at=now, state=state, app=app, website_domain=domain))
        )

    def _enqueue(self, sessions: list[dict]) -> list[dict]:
        for session in sessions:
            # Written to disk before anything tries to upload it. The reverse order
            # would lose a session whenever the process died mid-request.
            self.queue.enqueue(session)
        return sessions

    def run_sampler(self):
        while not self._stop.is_set():
            self.sample_once()
            self._sleep(SAMPLE_INTERVAL_SECONDS)
        # Whatever is open at shutdown ends now; it is real time that was observed.
        self._enqueue(self.builder.flush(self.clock()))

    # --- Screenshots ---------------------------------------------------------

    def screenshot_once(self) -> dict:
        """Capture one screenshot if due, then upload whatever is pending.

        Capture and upload share a cycle rather than two separate loops: the
        local queue is durable either way, so a capture that cannot upload
        immediately is retried on the next cycle, the same "write before you
        try to send it" ordering `_enqueue` uses for sessions.
        """
        if self.is_capturing_screenshots:
            try:
                image = self.screenshot_reader()
            except Exception:
                log.exception("Screenshot capture failed; skipping this tick")
                image = None
            if image:
                self.screenshot_queue.enqueue(self.clock().isoformat(), image)

        uploaded = 0
        if self.is_registered:
            for item in self.screenshot_queue.pending():
                try:
                    self.client.upload_screenshot(item["image"], item["captured_at"])
                except AgentApiError as exc:
                    if exc.status == 400:
                        # The upload itself is invalid (bad image, bad timestamp) —
                        # the backend's serializer validation, not a transport or
                        # auth problem. Not transient: keeping it at the head of the
                        # queue would block every capture behind it forever, so it
                        # is dropped and the next one is tried. 401/403/429 and
                        # network failures fall through to the retry path below,
                        # since those say nothing about this particular image.
                        self.screenshot_queue.discard(item["id"])
                        log.error(
                            "Server rejected screenshot %s; dropped locally: %s", item["id"], exc
                        )
                        continue
                    self.screenshot_queue.record_attempt(item["id"])
                    log.warning("Screenshot upload failed: %s", exc)
                    # Oldest-first: stop here rather than skip past a failure and
                    # upload a newer one out of order.
                    break
                self.screenshot_queue.mark_uploaded(item["id"])
                uploaded += 1
        return {"uploaded": uploaded, "pending": self.screenshot_queue.pending_count()}

    def run_screenshots(self):
        while not self._stop.is_set():
            try:
                self.screenshot_once()
            except Exception:
                # A bug here must not take heartbeat, sampling or session sync down
                # with it — the same independence every other loop already has.
                log.exception("Screenshot cycle failed; continuing")
            self._sleep(self.config.screenshot_interval_seconds)

    # --- Sync --------------------------------------------------------------

    def run_sync(self):
        # Clear out confirmed uploads left by previous runs before doing anything else,
        # so a machine that has been running for months does not accumulate a queue file
        # made entirely of history.
        self.queue.purge_synced()

        while not self._stop.is_set():
            delay = self.config.sync_interval_seconds
            if self.is_registered:
                with self._sync_lock:
                    result = self.sync_service.drain()
                if result["uploaded"] or result["rejected"]:
                    log.info(
                        "Synced %s session(s), %s duplicate(s), %s rejected, %s pending",
                        result["uploaded"],
                        result["duplicates"],
                        result["rejected"],
                        result["pending"],
                    )
                if result["uploaded"] or result["duplicates"]:
                    # Only when something was actually confirmed: that is the only way
                    # new synced rows appear.
                    self.queue.purge_synced()
                delay = self.sync_service.next_delay(self.config.sync_interval_seconds)
            self._sleep(delay)

    def sync_now(self) -> dict:
        """On-demand drain for the tray's "Sync now" — shares run_sync's lock rather
        than a separate call path, so this can never race the periodic one."""
        if not self.is_registered:
            raise NotRegistered("This device has not been enrolled yet.")
        with self._sync_lock:
            return self.sync_service.drain()

    def final_sync(self):
        """One last drain on the way out, so a clean quit does not leave a day queued."""
        if not self.is_registered:
            return
        try:
            self._enqueue(self.builder.flush(self.clock()))
            # run_sync's own drain may still be mid-flight at shutdown (stop() only
            # stops the loop *after* its current iteration) — the lock, not just the
            # stop flag, is what actually keeps this from overlapping it.
            with self._sync_lock:
                self.sync_service.drain(max_batches=5)
        except Exception:
            # Shutdown is the worst possible time to raise: the queue is durable, so
            # anything left behind uploads on the next start.
            log.exception("Final sync failed; sessions remain queued")

    # --- Loop --------------------------------------------------------------

    def run(self):
        """Heartbeat until stopped. Backs off on failure, never exits on error.

        The first successful beat of a run carries STARTUP, which is how the server
        learns that whatever session the previous run left open should be closed at that
        run's last heartbeat. Sending it from here rather than from the system-event
        watcher removes a race: a plain heartbeat arriving first would refresh "last
        seen" and hand the downtime to the session that was meant to be closed.
        """
        log.info("Agent %s starting for %s", __version__, self.config.server_url)
        announced_startup = False
        while not self._stop.is_set():
            delay = self.config.heartbeat_interval_seconds
            try:
                self.heartbeat(event=None if announced_startup else "STARTUP")
                # Only after one lands: a failed first beat must keep trying to
                # announce, or the recovery signal is lost for the whole run.
                announced_startup = True
            except NotRegistered:
                # Waiting for someone to type an enrollment code. Poll slowly; there is
                # nothing to report and nothing to retry.
                delay = max(self.config.heartbeat_interval_seconds, 30)
            except AgentApiError:
                delay = backoff_seconds(min(self.consecutive_failures - 1, 6))
                log.warning(
                    "Heartbeat failed (%s in a row); next attempt in %ss",
                    self.consecutive_failures,
                    delay,
                )
            self._sleep(delay)
        log.info("Agent stopped")

    def stop(self):
        self._stop.set()

    # --- Status ------------------------------------------------------------

    def status(self) -> dict:
        """What the tray menu and `--status` show."""
        queue_stats = self.queue.stats()
        return {
            "version": __version__,
            "server_url": self.config.server_url,
            "registered": self.is_registered,
            "computer_name": self.config.computer_name,
            "employee_name": self.config.employee_name,
            "state": self.last_state,
            "collecting": self.is_collecting,
            "heartbeat_interval_seconds": self.config.heartbeat_interval_seconds,
            "idle_threshold_seconds": self.config.idle_threshold_seconds,
            "sync_interval_seconds": self.config.sync_interval_seconds,
            "pending_sessions": queue_stats["pending"],
            "screenshot_capture_enabled": self.is_capturing_screenshots,
            "pending_screenshots": self.screenshot_queue.pending_count(),
            "last_error": self.last_error,
        }
