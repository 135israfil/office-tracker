"""Turning samples into closed sessions (§18).

The sampler produces a reading every couple of seconds; storing those directly would be
hundreds of thousands of rows per PC per day. This module converts a stream of samples
into *intervals* — "Visual Studio Code from 09:15:00 to 10:05:00" — which is what §18
asks for and what makes the reports cheap.

Four rules decide when an interval ends, and each exists because of a specific way the
data would otherwise lie:

1. **The value changed** — a different app, or active becoming idle. The obvious one.
2. **Idle closes the application track.** A PC left on overnight with an editor focused
   would otherwise report eight hours of "using Visual Studio Code". Idle time is real
   and recorded on its own track; it just is not application usage.
3. **A hard cap of 15 minutes.** A crash loses at most the current interval, so a power
   cut costs a quarter of an hour rather than a whole afternoon.
4. **A gap in the samples closes at the last sample, not at the resumption.** If the
   machine slept, or the agent was paused, nothing was observed in between — the same
   principle the server applies when it closes a session at the last heartbeat rather
   than at the moment it noticed.

Everything here is pure: samples in, closed sessions out, no clock of its own and no I/O.
That is what lets the awkward cases be tested rather than hoped about.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field

from .collectors.application import EMPTY, ForegroundApp
from .collectors.idle import STATE_IDLE

# §18 session types the agent produces. PC_ON is the server's to infer from heartbeats.
TYPE_ACTIVE = "ACTIVE"
TYPE_IDLE = "IDLE"
TYPE_APPLICATION = "APPLICATION"
TYPE_WEBSITE = "WEBSITE"

TRACK_STATE = "state"
TRACK_APPLICATION = "application"
TRACK_WEBSITE = "website"

# Rule 3. Fifteen minutes is the plan's figure: long enough that a busy day is a handful
# of rows per track, short enough that losing the open one is not a real loss.
MAX_SESSION_SECONDS = 15 * 60

# Rule 4. Three sampling intervals of silence means something stopped, not that the
# state persisted. Matches the server's three-missed-heartbeats rule for the same reason.
MAX_SAMPLE_GAP_SECONDS = 60

# Below this, an interval is an artefact of sampling rather than a fact about the day.
MIN_SESSION_SECONDS = 1


@dataclass(frozen=True)
class Sample:
    """One reading from the collectors."""

    at: dt.datetime
    state: str  # ONLINE or IDLE, as the idle collector reports it
    app: ForegroundApp = EMPTY
    # Bare domain of the foreground browser tab, or "" for anything else. Never a URL:
    # the browser collector truncates before this ever reaches the builder (§17).
    website_domain: str = ""

    @property
    def is_idle(self) -> bool:
        return self.state == STATE_IDLE


@dataclass
class _OpenSession:
    activity_type: str
    start_time: dt.datetime
    application_name: str = ""
    executable_name: str = ""
    website_domain: str = ""
    # Assigned at creation, not at upload: the id has to survive a crash between the two
    # for the server's idempotent upsert to mean anything.
    client_event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def key(self):
        """What makes this session the same session as the next sample's."""
        return (
            self.activity_type,
            self.application_name,
            self.executable_name,
            self.website_domain,
        )

    def close(self, at: dt.datetime) -> dict:
        end = max(at, self.start_time)
        return {
            "client_event_id": self.client_event_id,
            "activity_type": self.activity_type,
            "application_name": self.application_name,
            "executable_name": self.executable_name,
            "website_domain": self.website_domain,
            "start_time": self.start_time.isoformat(),
            "end_time": end.isoformat(),
            "duration_seconds": int((end - self.start_time).total_seconds()),
        }


class SessionBuilder:
    """Stateful, but only over the open sessions. Feed it samples, take closed ones."""

    def __init__(
        self,
        max_session_seconds: int = MAX_SESSION_SECONDS,
        max_sample_gap_seconds: int = MAX_SAMPLE_GAP_SECONDS,
    ):
        self.max_session_seconds = max_session_seconds
        self.max_sample_gap_seconds = max_sample_gap_seconds
        self._open: dict[str, _OpenSession] = {}
        self._last_sample_at: dt.datetime | None = None

    # --- Introspection (used by the tray status and tests) ------------------

    @property
    def open_tracks(self) -> dict[str, str]:
        return {track: session.activity_type for track, session in self._open.items()}

    # --- Core --------------------------------------------------------------

    def observe(self, sample: Sample) -> list[dict]:
        """Feed one sample in; get back whatever it closed."""
        closed = []

        if self._last_sample_at is not None:
            gap = (sample.at - self._last_sample_at).total_seconds()
            if gap > self.max_sample_gap_seconds or gap < 0:
                # Rule 4, and the same branch handles a clock that stepped backwards:
                # in both cases the open sessions describe a period we can no longer
                # vouch for, so they end where observation actually stopped.
                closed.extend(self._close_all(self._last_sample_at))

        self._last_sample_at = sample.at

        wanted = self._wanted_sessions(sample)
        for track in (TRACK_STATE, TRACK_APPLICATION, TRACK_WEBSITE):
            closed.extend(self._reconcile(track, wanted.get(track), sample.at))

        return [session for session in closed if session["duration_seconds"] >= MIN_SESSION_SECONDS]

    def flush(self, at: dt.datetime) -> list[dict]:
        """Close everything — on shutdown, on the kill switch, before a long pause."""
        closed = self._close_all(at)
        self._last_sample_at = None
        return [session for session in closed if session["duration_seconds"] >= MIN_SESSION_SECONDS]

    # --- Internals ---------------------------------------------------------

    def _wanted_sessions(self, sample: Sample) -> dict[str, _OpenSession | None]:
        state = _OpenSession(
            activity_type=TYPE_IDLE if sample.is_idle else TYPE_ACTIVE,
            start_time=sample.at,
        )

        application = None
        # Rule 2: no application track while idle, and none when there is no foreground
        # window to attribute time to (the lock screen, a desktop switch).
        if not sample.is_idle and not sample.app.is_empty:
            application = _OpenSession(
                activity_type=TYPE_APPLICATION,
                start_time=sample.at,
                application_name=sample.app.application_name,
                executable_name=sample.app.executable_name,
            )

        website = None
        # A website session needs an active user and a domain. It rides alongside the
        # application session for the browser rather than replacing it: §18's tracks run
        # in parallel, and "Chrome for 2h" and "github.com for 25m" are both true.
        if not sample.is_idle and sample.website_domain:
            website = _OpenSession(
                activity_type=TYPE_WEBSITE,
                start_time=sample.at,
                website_domain=sample.website_domain,
            )

        return {
            TRACK_STATE: state,
            TRACK_APPLICATION: application,
            TRACK_WEBSITE: website,
        }

    def _reconcile(self, track: str, wanted: _OpenSession | None, at: dt.datetime) -> list[dict]:
        current = self._open.get(track)
        closed = []

        if current is not None and wanted is not None and current.key() == wanted.key():
            if (at - current.start_time).total_seconds() >= self.max_session_seconds:
                # Rule 3: same value, but long enough that leaving it open risks losing
                # it. Close and immediately reopen; the reports sum within a type.
                closed.append(current.close(at))
                self._open[track] = _OpenSession(
                    activity_type=current.activity_type,
                    start_time=at,
                    application_name=current.application_name,
                    executable_name=current.executable_name,
                    website_domain=current.website_domain,
                )
            return closed

        if current is not None:
            closed.append(current.close(at))
            self._open.pop(track, None)

        if wanted is not None:
            self._open[track] = wanted
        return closed

    def _close_all(self, at: dt.datetime) -> list[dict]:
        closed = [session.close(at) for session in self._open.values()]
        self._open.clear()
        return closed
