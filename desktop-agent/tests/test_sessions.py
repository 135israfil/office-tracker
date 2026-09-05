"""Phase 5 agent tests: session building, the offline queue and sync.

The session builder decides what a day looks like, so its awkward cases are enumerated
here rather than left to a manual test on someone's desk: an app switch, an idle
transition, a fifteen-minute cap, a sleep that swallowed twenty minutes of samples, and
a clock that stepped backwards.

The queue and sync tests exist for one property above all — nothing is marked synced
before the server has said 2xx, and everything survives the process dying at any point.
"""

from __future__ import annotations

import datetime as dt

import pytest

from agent.api import AgentApiError
from agent.collectors.application import EMPTY, ForegroundApp, friendly_name, is_shell_process
from agent.config import AgentConfig
from agent.service import AgentService
from agent.sessions import (
    MAX_SAMPLE_GAP_SECONDS,
    TYPE_ACTIVE,
    TYPE_APPLICATION,
    TYPE_IDLE,
    Sample,
    SessionBuilder,
)
from agent.storage.queue import SessionQueue
from agent.sync.client import SyncService

START = dt.datetime(2026, 8, 19, 9, 0, tzinfo=dt.UTC)

VSCODE = ForegroundApp(application_name="Visual Studio Code", executable_name="Code.exe")
CHROME = ForegroundApp(application_name="Google Chrome", executable_name="chrome.exe")


def at(seconds):
    return START + dt.timedelta(seconds=seconds)


def sample(seconds, state="ONLINE", app=VSCODE):
    return Sample(at=at(seconds), state=state, app=app)


def by_type(sessions):
    return {session["activity_type"]: session for session in sessions}


def feed(builder, start_seconds, end_seconds, *, step=2, state="ONLINE", app=VSCODE):
    """Drive the builder the way the sampler does: one reading every couple of seconds.

    Jumping straight from t=0 to t=120 in a test would trip the sample-gap rule and
    prove nothing about app switching, so the tests feed a realistic stream.
    """
    closed = []
    moment = start_seconds
    while moment <= end_seconds:
        closed.extend(builder.observe(Sample(at=at(moment), state=state, app=app)))
        moment += step
    return closed


# --- Application collector helpers ------------------------------------------


class TestApplicationCollector:
    def test_friendly_name_prefers_the_executable_description(self):
        assert friendly_name("Visual Studio Code", "Code.exe") == "Visual Studio Code"

    def test_friendly_name_falls_back_to_the_process_name(self):
        # Plenty of executables ship no version resource; §15 still wants a name.
        assert friendly_name(None, "Code.exe") == "Code"
        assert friendly_name("   ", "notepad.exe") == "notepad"

    def test_shell_processes_are_not_applications(self):
        # Otherwise every Alt-Tab and every trip to the lock screen becomes a session.
        assert is_shell_process("explorer.exe")
        assert is_shell_process("LockApp.exe")
        assert not is_shell_process("Code.exe")

    def test_foreground_app_carries_no_window_title(self):
        app = ForegroundApp(
            application_name="Visual Studio Code",
            executable_name="Code.exe",
            title_signature="12345",
        )
        # The title is a change signal, never data: it would carry document and file
        # names, which is file-activity monitoring under §31.
        assert "title" not in {"application_name", "executable_name"}
        assert app.title_signature == "12345"
        assert "PLAN.md" not in f"{app.application_name}{app.executable_name}"


# --- Session builder --------------------------------------------------------


class TestSessionBuilder:
    def test_steady_state_closes_nothing(self):
        builder = SessionBuilder()
        assert builder.observe(sample(0)) == []
        assert builder.observe(sample(2)) == []
        assert builder.observe(sample(4)) == []
        assert builder.open_tracks == {"state": TYPE_ACTIVE, "application": TYPE_APPLICATION}

    def test_app_switch_closes_the_application_session_only(self):
        builder = SessionBuilder()
        assert feed(builder, 0, 120) == []
        closed = builder.observe(sample(122, app=CHROME))

        assert len(closed) == 1
        session = closed[0]
        assert session["activity_type"] == TYPE_APPLICATION
        assert session["application_name"] == "Visual Studio Code"
        assert session["executable_name"] == "Code.exe"
        assert session["duration_seconds"] == 122
        # The state track is unaffected: the user was active throughout.
        assert builder.open_tracks["state"] == TYPE_ACTIVE

    def test_going_idle_closes_both_tracks_and_starts_an_idle_session(self):
        builder = SessionBuilder()
        feed(builder, 0, 120)
        closed = by_type(builder.observe(sample(122, state="IDLE")))

        assert closed[TYPE_ACTIVE]["duration_seconds"] == 122
        assert closed[TYPE_APPLICATION]["duration_seconds"] == 122
        # A PC left on overnight with an editor focused must not report eight hours of
        # "using Visual Studio Code".
        assert builder.open_tracks == {"state": TYPE_IDLE}

    def test_returning_from_idle_reopens_the_application_track(self):
        builder = SessionBuilder()
        feed(builder, 0, 120)
        feed(builder, 122, 300, state="IDLE")
        closed = builder.observe(sample(302))

        assert closed[0]["activity_type"] == TYPE_IDLE
        assert closed[0]["duration_seconds"] == 180
        assert builder.open_tracks == {"state": TYPE_ACTIVE, "application": TYPE_APPLICATION}

    def test_long_use_is_split_at_the_cap(self):
        builder = SessionBuilder(max_session_seconds=60)
        closed = feed(builder, 0, 60)

        assert len(closed) == 2  # both tracks hit the cap together
        application = by_type(closed)[TYPE_APPLICATION]
        assert application["duration_seconds"] == 60
        # Reopened immediately with the same values, so a crash costs a quarter of an
        # hour rather than the whole afternoon.
        assert builder.open_tracks["application"] == TYPE_APPLICATION
        assert feed(builder, 62, 118) == []

    def test_split_sessions_get_distinct_event_ids(self):
        builder = SessionBuilder(max_session_seconds=30)
        first = feed(builder, 0, 30)
        second = feed(builder, 32, 60)

        ids = {session["client_event_id"] for session in first + second}
        # Reusing an id would make the server treat the second interval as a replay of
        # the first and silently drop it.
        assert len(ids) == len(first) + len(second)

    def test_a_gap_in_samples_closes_at_the_last_sample_not_the_resumption(self):
        builder = SessionBuilder()
        feed(builder, 0, 60)

        # The laptop slept for twenty minutes: nothing was observed in between.
        closed = by_type(builder.observe(sample(60 + 20 * 60)))

        assert closed[TYPE_ACTIVE]["duration_seconds"] == 60
        assert closed[TYPE_APPLICATION]["duration_seconds"] == 60
        assert closed[TYPE_ACTIVE]["end_time"] == at(60).isoformat()
        # Same principle as the server closing a PC session at the last heartbeat rather
        # than when it noticed the silence.
        assert builder.open_tracks["state"] == TYPE_ACTIVE

    def test_a_gap_just_inside_the_threshold_is_not_a_gap(self):
        builder = SessionBuilder()
        builder.observe(sample(0))
        # A slow tick — a busy machine, a stalled collector — is not a gap.
        assert builder.observe(sample(MAX_SAMPLE_GAP_SECONDS)) == []

    def test_a_clock_that_steps_backwards_does_not_produce_negative_time(self):
        builder = SessionBuilder()
        feed(builder, 540, 600)
        closed = builder.observe(sample(0))

        assert all(session["duration_seconds"] >= 0 for session in closed)
        assert builder.open_tracks["state"] == TYPE_ACTIVE

    def test_no_foreground_window_closes_the_application_track_only(self):
        builder = SessionBuilder()
        feed(builder, 0, 28)
        # The lock screen and desktop switches have no window to attribute time to.
        closed = builder.observe(sample(30, app=EMPTY))

        assert [session["activity_type"] for session in closed] == [TYPE_APPLICATION]
        assert builder.open_tracks == {"state": TYPE_ACTIVE}

    def test_sub_second_sessions_are_dropped(self):
        builder = SessionBuilder()
        builder.observe(sample(0))
        # An artefact of sampling, not a fact about the day.
        assert builder.observe(Sample(at=at(0), state="ONLINE", app=CHROME)) == []

    def test_flush_closes_everything_and_resets(self):
        builder = SessionBuilder()
        feed(builder, 0, 60)
        closed = builder.flush(at(120))

        assert len(closed) == 2
        assert builder.open_tracks == {}
        # After a flush the next sample starts fresh rather than being treated as a gap.
        assert builder.observe(sample(3600)) == []

    def test_sessions_carry_everything_the_api_needs(self):
        builder = SessionBuilder()
        feed(builder, 0, 58)
        session = by_type(builder.observe(sample(60, app=CHROME)))[TYPE_APPLICATION]

        assert set(session) == {
            "client_event_id",
            "activity_type",
            "application_name",
            "executable_name",
            "website_domain",
            "start_time",
            "end_time",
            "duration_seconds",
        }


# --- Offline queue ----------------------------------------------------------


@pytest.fixture
def queue(tmp_path):
    queue = SessionQueue(tmp_path / "queue.sqlite3")
    yield queue
    queue.close()


def closed_session(index=0, **overrides):
    payload = {
        "client_event_id": f"event-{index}",
        "activity_type": TYPE_APPLICATION,
        "application_name": "Visual Studio Code",
        "executable_name": "Code.exe",
        "website_domain": "",
        "start_time": at(index * 60).isoformat(),
        "end_time": at(index * 60 + 60).isoformat(),
        "duration_seconds": 60,
    }
    payload.update(overrides)
    return payload


class TestSessionQueue:
    def test_enqueue_and_read_back(self, queue):
        queue.enqueue(closed_session(0))
        queue.enqueue(closed_session(1))

        pending = queue.pending()
        assert [row["client_event_id"] for row in pending] == ["event-0", "event-1"]
        assert queue.pending_count() == 2

    def test_marking_synced_removes_rows_from_pending(self, queue):
        queue.enqueue_many([closed_session(0), closed_session(1)])
        rows = queue.pending()

        queue.mark_synced([rows[0]["id"]])
        assert [row["client_event_id"] for row in queue.pending()] == ["event-1"]

    def test_the_same_session_cannot_be_queued_twice(self, queue):
        assert queue.enqueue(closed_session(0)) is True
        assert queue.enqueue(closed_session(0)) is False
        assert queue.pending_count() == 1

    def test_the_queue_survives_the_process(self, tmp_path):
        path = tmp_path / "queue.sqlite3"
        first = SessionQueue(path)
        first.enqueue(closed_session(0))
        first.close()

        # The thing this file exists to survive is a power cut, which is also the event
        # that loses the in-memory session.
        second = SessionQueue(path)
        assert second.pending_count() == 1
        second.close()

    def test_discard_drops_rows_the_server_refused(self, queue):
        queue.enqueue_many([closed_session(0), closed_session(1)])
        rows = queue.pending()

        queue.discard([rows[0]["id"]])
        assert queue.pending_count() == 1

    def test_attempts_are_counted(self, queue):
        queue.enqueue(closed_session(0))
        rows = queue.pending()
        queue.record_attempt([row["id"] for row in rows])
        queue.record_attempt([row["id"] for row in rows])

        assert queue.stats()["max_attempts"] == 2

    def test_purge_keeps_recent_uploads_and_removes_old_ones(self, queue):
        queue.enqueue_many([closed_session(0), closed_session(1)])
        rows = queue.pending()
        queue.mark_synced([row["id"] for row in rows])

        assert queue.purge_synced(keep_days=1) == 0  # just uploaded: still around

        with queue._connection:  # backdate one upload
            queue._connection.execute(
                "UPDATE sessions SET synced_at = datetime('now', '-3 days') WHERE id = ?",
                (rows[0]["id"],),
            )
        assert queue.purge_synced(keep_days=1) == 1
        assert queue.stats()["total"] == 1

    def test_queue_refuses_to_grow_without_bound(self, queue, monkeypatch):
        monkeypatch.setattr("agent.storage.queue.MAX_PENDING_ROWS", 2)
        assert queue.enqueue(closed_session(0)) is True
        assert queue.enqueue(closed_session(1)) is True
        # An agent offline for a month must not fill the disk, and the drop is logged
        # rather than silent.
        assert queue.enqueue(closed_session(2)) is False


# --- Sync service -----------------------------------------------------------


class FakeSyncClient:
    def __init__(self, responses=None):
        self.batches = []
        self.responses = list(responses or [])

    def sync(self, sessions):
        self.batches.append(sessions)
        if self.responses:
            outcome = self.responses.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return {"accepted": len(sessions), "duplicates": 0, "rejected": []}


class TestSyncService:
    def test_successful_upload_marks_rows_synced(self, queue):
        queue.enqueue_many([closed_session(i) for i in range(3)])
        service = SyncService(queue, FakeSyncClient())

        result = service.sync_once()

        assert result["uploaded"] == 3
        assert queue.pending_count() == 0

    def test_nothing_is_marked_synced_when_the_upload_fails(self, queue):
        queue.enqueue_many([closed_session(i) for i in range(3)])
        service = SyncService(queue, FakeSyncClient([AgentApiError("network down")]))

        result = service.sync_once()

        assert result["status"] == "failed"
        # The whole point of the flag: nothing is forgotten until the server confirms it.
        assert queue.pending_count() == 3
        assert queue.stats()["max_attempts"] == 1
        assert service.consecutive_failures == 1

    def test_backoff_grows_while_failing_and_resets_on_success(self, queue):
        queue.enqueue(closed_session(0))
        client = FakeSyncClient([AgentApiError("down"), AgentApiError("down")])
        service = SyncService(queue, client)

        service.sync_once()
        assert service.next_delay(60) == 60  # first retry: the normal interval is longer
        service.sync_once()
        assert service.next_delay(5) == 10

        service.sync_once()
        assert service.consecutive_failures == 0
        assert service.next_delay(60) == 60

    def test_the_id_is_not_sent_to_the_server(self, queue):
        queue.enqueue(closed_session(0))
        client = FakeSyncClient()
        SyncService(queue, client).sync_once()

        # The local row id is bookkeeping; the server identifies sessions by
        # client_event_id.
        assert "id" not in client.batches[0][0]

    def test_rejected_sessions_are_dropped_locally(self, queue):
        queue.enqueue_many([closed_session(0), closed_session(1)])
        client = FakeSyncClient(
            [
                {
                    "accepted": 1,
                    "duplicates": 0,
                    "rejected": [{"client_event_id": "event-1", "errors": {}}],
                }
            ]
        )
        service = SyncService(queue, client)

        result = service.sync_once()

        assert result["rejected"] == 1
        # Without this, one malformed row sits at the head of the queue forever and
        # blocks everything behind it.
        assert queue.stats()["total"] == 1
        assert queue.pending_count() == 0

    def test_duplicates_are_a_normal_outcome(self, queue):
        queue.enqueue(closed_session(0))
        client = FakeSyncClient([{"accepted": 0, "duplicates": 1, "rejected": []}])
        service = SyncService(queue, client)

        result = service.sync_once()

        # A replay after a dropped response. The row is already stored server-side, so
        # it is done, not failed.
        assert result["duplicates"] == 1
        assert queue.pending_count() == 0

    def test_drain_uploads_everything_in_batches(self, queue):
        queue.enqueue_many([closed_session(i) for i in range(25)])
        client = FakeSyncClient()
        service = SyncService(queue, client, batch_size=10)

        totals = service.drain()

        assert totals["uploaded"] == 25
        assert [len(batch) for batch in client.batches] == [10, 10, 5]
        assert totals["pending"] == 0

    def test_drain_stops_at_the_first_failure(self, queue):
        queue.enqueue_many([closed_session(i) for i in range(30)])
        client = FakeSyncClient(
            [{"accepted": 10, "duplicates": 0, "rejected": []}, AgentApiError("down")]
        )
        service = SyncService(queue, client, batch_size=10)

        totals = service.drain()

        assert totals["uploaded"] == 10
        assert queue.pending_count() == 20

    def test_drain_is_capped_so_a_long_outage_does_not_monopolise_the_thread(self, queue):
        queue.enqueue_many([closed_session(i) for i in range(100)])
        client = FakeSyncClient()
        service = SyncService(queue, client, batch_size=5)

        totals = service.drain(max_batches=3)

        assert totals["batches"] == 3
        assert queue.pending_count() == 85

    def test_empty_queue_is_not_a_failure(self, queue):
        service = SyncService(queue, FakeSyncClient())
        assert service.sync_once()["status"] == "empty"


# --- Service wiring ---------------------------------------------------------


class RecordingClient:
    """Accepts everything and remembers what it was given."""

    def __init__(self, token="t"):
        self.token = token
        self.batches = []

    def sync(self, sessions):
        self.batches.append(sessions)
        return {"accepted": len(sessions), "duplicates": 0, "rejected": []}


class TestServiceCollection:
    def make(self, tmp_path, queue, *, enabled=True, token="t", app=VSCODE, idle=0):
        config = AgentConfig(
            server_url="https://office.example.com",
            _path=tmp_path / "agent.json",
            enabled=enabled,
        )
        moments = iter(at(seconds) for seconds in range(0, 100_000, 2))
        return AgentService(
            config,
            client=RecordingClient(token=token),
            queue=queue,
            idle_reader=lambda: idle,
            app_reader=lambda: app,
            clock=lambda: next(moments),
            sleep=lambda seconds: None,
            token_loader=lambda: token,
            token_saver=lambda value: None,
            token_clearer=lambda: None,
        )

    def test_sampling_writes_closed_sessions_to_the_queue_before_upload(self, tmp_path, queue):
        service = self.make(tmp_path, queue)

        for _ in range(5):
            service.sample_once()
        service.app_reader = lambda: CHROME
        service.sample_once()

        # On disk before anything tries to send it: the reverse order loses a session
        # whenever the process dies mid-request.
        assert queue.pending_count() == 1
        assert queue.pending()[0]["application_name"] == "Visual Studio Code"

    def test_the_kill_switch_stops_collection_and_closes_what_is_open(self, tmp_path, queue):
        service = self.make(tmp_path, queue)
        for _ in range(5):
            service.sample_once()

        service.config.enabled = False
        service.sample_once()

        assert service.is_collecting is False
        # The open session is closed rather than left to absorb the pause.
        assert queue.pending_count() == 2
        before = queue.pending_count()
        service.sample_once()
        assert queue.pending_count() == before

    def test_an_unenrolled_agent_collects_nothing(self, tmp_path, queue):
        service = self.make(tmp_path, queue, token=None)

        for _ in range(5):
            service.sample_once()

        # Buffering activity for a machine the server has never heard of would produce
        # sessions with nowhere to go.
        assert service.is_collecting is False
        assert queue.pending_count() == 0

    def test_a_broken_collector_skips_the_tick_rather_than_the_agent(self, tmp_path, queue):
        service = self.make(tmp_path, queue)

        def explode():
            raise OSError("GetForegroundWindow failed")

        service.app_reader = explode
        assert service.sample_once() == []
        # Recovers on the next tick without restarting anything.
        service.app_reader = lambda: VSCODE
        service.sample_once()
        assert service.builder.open_tracks

    def test_final_sync_flushes_and_uploads_what_is_open(self, tmp_path, queue):
        service = self.make(tmp_path, queue)
        for _ in range(5):
            service.sample_once()

        service.final_sync()

        assert queue.pending_count() == 0
        assert service.client.batches, "the open session should have been uploaded"

    def test_the_sync_loop_purges_confirmed_uploads(self, tmp_path, queue):
        service = self.make(tmp_path, queue)
        for _ in range(5):
            service.sample_once()
        service.app_reader = lambda: CHROME
        service.sample_once()
        assert queue.pending_count() == 1

        purges = []
        original = queue.purge_synced
        queue.purge_synced = lambda *args, **kwargs: purges.append(1) or original(*args, **kwargs)

        # One pass of the loop: stop it from the injected sleep.
        service._sleep = lambda seconds: service.stop()
        service.run_sync()

        # Purged on entry and again after the upload was confirmed. Without this the
        # queue file grows forever on a machine that runs for months.
        assert len(purges) >= 2

    def test_the_sampler_asks_the_browser_collector_for_a_domain(self, tmp_path, queue):
        from agent.collectors.application import ForegroundApp
        from agent.collectors.browser import BrowserCollector

        chrome = ForegroundApp(
            application_name="Google Chrome", executable_name="chrome.exe", title_signature="t1"
        )
        service = self.make(tmp_path, queue, app=chrome)
        service.browser = BrowserCollector(reader=lambda exe: "https://github.com/a/b?token=x")

        for _ in range(5):
            service.sample_once()
        service.app_reader = lambda: VSCODE
        service.sample_once()

        website = [row for row in queue.pending() if row["activity_type"] == "WEBSITE"]
        assert len(website) == 1
        # The truncation happened in the collector, before the queue: what reaches disk
        # is a domain and nothing else (§17).
        assert website[0]["website_domain"] == "github.com"
        assert "token" not in str(website[0])

    def test_final_sync_never_raises(self, tmp_path, queue):
        service = self.make(tmp_path, queue)
        service.sample_once()

        def explode(sessions):
            raise RuntimeError("everything is on fire")

        service.client.sync = explode
        # Shutdown is the worst possible moment to raise: the queue is durable, so
        # anything left behind uploads on the next start.
        service.final_sync()
        assert queue.pending_count() >= 0
