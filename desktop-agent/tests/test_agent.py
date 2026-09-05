"""Agent unit tests.

Everything Windows-specific is behind a pure function, and those are what is tested
here: tick-wrap arithmetic, message-to-event mapping, backoff, URL normalisation, and
the service loop with an injected fake client. What is left needs a real Windows box and
lives in the manual matrix in the README.

The privacy-adjacent assertions — that the device token never reaches disk — are tests
rather than review notes on purpose. A regression there would be silent.
"""

from __future__ import annotations

import json

import pytest

from agent.api import AgentApiError, AgentClient, backoff_seconds, normalise_server_url
from agent.collectors.idle import (
    STATE_IDLE,
    STATE_ONLINE,
    elapsed_ticks,
    heartbeat_state,
    idle_seconds,
)
from agent.collectors.system import (
    EVENT_LOCK,
    EVENT_SHUTDOWN,
    EVENT_SLEEP,
    EVENT_UNLOCK,
    EVENT_WAKE,
    PBT_APMRESUMEAUTOMATIC,
    PBT_APMRESUMESUSPEND,
    PBT_APMSUSPEND,
    WM_ENDSESSION,
    WM_POWERBROADCAST,
    WM_QUERYENDSESSION,
    WM_WTSSESSION_CHANGE,
    WTS_SESSION_LOCK,
    WTS_SESSION_UNLOCK,
    lifecycle_event,
)
from agent.config import AgentConfig, TokenStorageError
from agent.machine import machine_info, windows_name
from agent.service import AgentService, NotRegistered
from agent.single_instance import AlreadyRunning, SingleInstance
from agent.storage.queue import SessionQueue
from agent.tray import status_text


@pytest.fixture
def config(tmp_path):
    return AgentConfig(server_url="https://office.example.com", _path=tmp_path / "agent.json")


@pytest.fixture
def queue(tmp_path):
    """A throwaway queue.

    Injected everywhere rather than left to the default, which would open a database in
    the real `%PROGRAMDATA%` installation directory the moment a test asked for status.
    """
    queue = SessionQueue(tmp_path / "queue.sqlite3")
    yield queue
    queue.close()


class FakeClient:
    """Stands in for AgentClient. Records calls, replays scripted outcomes."""

    def __init__(self, token=None, responses=None):
        self.token = token
        self.calls = []
        self.responses = list(responses or [])

    def _next(self, default):
        if not self.responses:
            return default
        outcome = self.responses.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def register(self, code, machine):
        self.calls.append(("register", code, machine))
        result = self._next(
            {
                "device_token": "token-abc",
                "computer": {"id": 7, "computer_name": "DEV-PC-01", "employee_name": "Rahim"},
                "config": {"heartbeat_interval_seconds": 30},
            }
        )
        self.token = result.get("device_token")
        return result

    def heartbeat(self, state="ONLINE", event=None, timeout=None):
        self.calls.append(("heartbeat", state, event, timeout))
        return self._next({"status": "ONLINE", "config": {}})

    def get_config(self):
        self.calls.append(("config",))
        return self._next({})

    def sync(self, sessions):
        self.calls.append(("sync", sessions))
        return self._next({"accepted": len(sessions), "duplicates": 0, "rejected": []})


# --- Idle -------------------------------------------------------------------


class TestIdle:
    def test_elapsed_ticks_handles_the_normal_case(self):
        assert elapsed_ticks(1_000, 4_000) == 3_000

    def test_elapsed_ticks_survives_the_49_day_wrap(self):
        # The Phase 1 spike finding: GetTickCount is 32-bit and wraps every ~49.7 days.
        # Unmasked, this subtraction is negative and the agent decides the user has been
        # idle since before the machine existed.
        just_before_wrap = 0xFFFFFFFF - 500
        just_after_wrap = 1_500
        assert elapsed_ticks(just_before_wrap, just_after_wrap) == 2_001

    def test_state_uses_the_configured_threshold(self):
        assert heartbeat_state(299, 300) == STATE_ONLINE
        assert heartbeat_state(300, 300) == STATE_IDLE
        assert heartbeat_state(1_000, 300) == STATE_IDLE

    def test_idle_seconds_is_harmless_off_windows(self):
        # CI runs on Linux; the collector must not explode, and must not invent idleness.
        assert idle_seconds() >= 0.0


# --- System events ----------------------------------------------------------


class TestLifecycleMapping:
    @pytest.mark.parametrize(
        ("message", "wparam", "expected"),
        [
            (WM_QUERYENDSESSION, 0, EVENT_SHUTDOWN),
            (WM_POWERBROADCAST, PBT_APMSUSPEND, EVENT_SLEEP),
            (WM_POWERBROADCAST, PBT_APMRESUMESUSPEND, EVENT_WAKE),
            (WM_POWERBROADCAST, PBT_APMRESUMEAUTOMATIC, EVENT_WAKE),
            (WM_WTSSESSION_CHANGE, WTS_SESSION_LOCK, EVENT_LOCK),
            (WM_WTSSESSION_CHANGE, WTS_SESSION_UNLOCK, EVENT_UNLOCK),
        ],
    )
    def test_known_messages_map_to_events(self, message, wparam, expected):
        assert lifecycle_event(message, wparam) == expected

    @pytest.mark.parametrize(
        ("message", "wparam"),
        [
            (WM_POWERBROADCAST, 0x99),  # battery/power-source changes are not our business
            (WM_WTSSESSION_CHANGE, 0x1),  # console connect
            (WM_ENDSESSION, 0),  # already reported by WM_QUERYENDSESSION
            (0x0001, 0),
        ],
    )
    def test_everything_else_is_ignored(self, message, wparam):
        assert lifecycle_event(message, wparam) is None


# --- Machine identity -------------------------------------------------------


class TestMachine:
    def test_windows_11_is_distinguished_by_build_number(self):
        # platform.release() says "10" on Windows 11; only the build tells them apart.
        assert windows_name("10", 22631) == "Windows 11"
        assert windows_name("10", 19045) == "Windows 10"
        assert windows_name("10", None) == "Windows 10"
        assert windows_name("", None) == "Windows"

    def test_machine_info_has_what_registration_needs(self):
        info = machine_info()
        assert set(info) == {"computer_name", "operating_system", "agent_version"}
        assert info["computer_name"]


# --- API client -------------------------------------------------------------


class TestApiClient:
    def test_backoff_grows_then_stops(self):
        assert [backoff_seconds(n) for n in range(4)] == [5, 10, 20, 40]
        assert backoff_seconds(20) == 300  # capped, not astronomical
        with pytest.raises(ValueError):
            backoff_seconds(-1)

    def test_server_url_normalisation(self):
        assert normalise_server_url("https://office.example.com/") == "https://office.example.com"
        assert (
            normalise_server_url("https://office.example.com/api") == "https://office.example.com"
        )
        # A bare hostname must not silently become http:// — that would put the device
        # token on the wire in plaintext, against §29.
        assert normalise_server_url("office.example.com") == "https://office.example.com"
        assert normalise_server_url("http://localhost:8000") == "http://localhost:8000"
        with pytest.raises(ValueError):
            normalise_server_url("  ")

    def test_endpoint_paths(self):
        client = AgentClient("https://office.example.com", token="t")
        assert client._url("heartbeat") == "https://office.example.com/api/agent/heartbeat/"

    def test_an_empty_server_url_is_accepted_at_construction(self):
        """A freshly installed machine that has never been given a server URL must still
        be able to construct a client (and, via that, an AgentService, and via that, a
        tray) — the alternative is the whole process failing to start at all, silently,
        because this is a windowed build with no console to show the error on."""
        client = AgentClient("")
        assert client.server_url == ""

    def test_an_empty_server_url_fails_only_when_actually_used(self):
        client = AgentClient("", token="t")
        with pytest.raises(AgentApiError, match="No server URL configured"):
            client.heartbeat()

    def test_unregistered_client_refuses_authenticated_calls(self):
        client = AgentClient("https://office.example.com")
        with pytest.raises(AgentApiError) as exc:
            client.heartbeat()
        assert exc.value.status == 401

    def test_http_errors_carry_the_status_and_detail(self):
        class Response:
            status_code = 400
            content = b'{"detail": "Unknown or already-used enrollment code."}'

            def json(self):
                return json.loads(self.content)

        class Session:
            headers = {}

            def request(self, *args, **kwargs):
                return Response()

        client = AgentClient("https://office.example.com", session=Session())
        with pytest.raises(AgentApiError) as exc:
            client.register("BAD", {})
        assert exc.value.status == 400
        assert "already-used" in str(exc.value)

    def test_auth_failures_are_recognisable(self):
        assert AgentApiError("x", status=401).is_auth_failure
        assert AgentApiError("x", status=403).is_auth_failure
        assert not AgentApiError("x", status=500).is_auth_failure
        assert not AgentApiError("network down").is_auth_failure


# --- Config and credentials -------------------------------------------------


class TestConfig:
    def test_round_trip(self, tmp_path):
        path = tmp_path / "agent.json"
        AgentConfig(server_url="https://office.example.com", computer_id=3, _path=path).save()

        loaded = AgentConfig.load(path)
        assert loaded.server_url == "https://office.example.com"
        assert loaded.computer_id == 3

    def test_unknown_keys_from_a_newer_agent_are_ignored(self, tmp_path):
        path = tmp_path / "agent.json"
        path.write_text(json.dumps({"server_url": "https://x", "future_option": True}))
        # A staged rollout must not brick the older build on a machine.
        assert AgentConfig.load(path).server_url == "https://x"

    def test_missing_file_yields_defaults(self, tmp_path):
        config = AgentConfig.load(tmp_path / "nothing.json")
        assert config.heartbeat_interval_seconds == 60
        assert config.is_configured is False

    def test_server_config_is_adopted_and_persisted(self, config):
        changed = config.apply_server_config(
            {
                "heartbeat_interval_seconds": 30,
                "idle_threshold_seconds": 600,
                "enabled": False,
                "config_version": 12345,
            }
        )
        assert changed is True
        assert config.heartbeat_interval_seconds == 30
        assert config.enabled is False
        # Re-applying the same payload is not a change, so it does not churn the file.
        assert config.apply_server_config({"heartbeat_interval_seconds": 30}) is False

        assert AgentConfig.load(config._path).idle_threshold_seconds == 600

    def test_token_is_never_written_to_the_config_file(self, tmp_path, monkeypatch):
        """The one privacy invariant of this module, asserted rather than assumed."""
        stored = {}
        monkeypatch.setattr(
            "agent.config._keyring",
            lambda: type(
                "K",
                (),
                {
                    "set_password": staticmethod(
                        lambda service, user, value: stored.setdefault(user, value)
                    ),
                    "get_password": staticmethod(lambda service, user: stored.get(user)),
                    "delete_password": staticmethod(lambda service, user: stored.pop(user, None)),
                },
            )(),
        )
        from agent import config as config_module

        config_module.store_token("super-secret-token")
        path = tmp_path / "agent.json"
        AgentConfig(server_url="https://x", computer_id=1, _path=path).save()

        assert config_module.load_token() == "super-secret-token"
        assert "super-secret-token" not in path.read_text()

    def test_empty_token_is_refused(self):
        with pytest.raises(TokenStorageError):
            from agent import config as config_module

            config_module.store_token("")


# --- Service ----------------------------------------------------------------


class TestService:
    def make(self, config, client, queue=None, **kwargs):
        tokens = {}
        return AgentService(
            config,
            client=client,
            queue=queue,
            idle_reader=kwargs.pop("idle_reader", lambda: 0),
            sleep=kwargs.pop("sleep", lambda seconds: None),
            token_loader=lambda: tokens.get("token"),
            token_saver=lambda value: tokens.__setitem__("token", value),
            token_clearer=lambda: tokens.pop("token", None),
            **kwargs,
        )

    def test_enrolment_stores_the_token_and_adopts_the_config(self, config):
        client = FakeClient()
        service = self.make(config, client)

        service.enroll("ABCDE-FGHJK")

        assert service.is_registered
        assert config.computer_id == 7
        assert config.employee_name == "Rahim"
        assert config.heartbeat_interval_seconds == 30

    def test_enrolment_without_a_token_is_an_error(self, config):
        client = FakeClient(responses=[{"computer": {}, "config": {}}])
        service = self.make(config, client)
        with pytest.raises(AgentApiError):
            service.enroll("ABCDE-FGHJK")

    def test_heartbeat_reports_idle_state_from_the_configured_threshold(self, config):
        config.idle_threshold_seconds = 300
        client = FakeClient(token="t")
        service = self.make(config, client, idle_reader=lambda: 400)

        service.heartbeat()
        assert client.calls[-1][1] == STATE_IDLE

    def test_a_broken_idle_reader_still_reports_liveness(self, config):
        def explode():
            raise OSError("GetLastInputInfo failed")

        client = FakeClient(token="t")
        service = self.make(config, client, idle_reader=explode)

        service.heartbeat()
        # A PC that cannot measure idleness is still a PC that is on.
        assert client.calls[-1][1] == STATE_ONLINE

    def test_heartbeat_without_a_token_raises_not_registered(self, config):
        service = self.make(config, FakeClient())
        with pytest.raises(NotRegistered):
            service.heartbeat()

    def test_revoked_credential_is_forgotten_rather_than_retried_forever(self, config):
        client = FakeClient(token="t", responses=[AgentApiError("gone", status=401)])
        service = self.make(config, client)

        with pytest.raises(AgentApiError):
            service.heartbeat()
        assert service.is_registered is False

    def test_transport_failure_keeps_the_credential(self, config):
        client = FakeClient(token="t", responses=[AgentApiError("network down")])
        service = self.make(config, client)

        with pytest.raises(AgentApiError):
            service.heartbeat()
        # A dropped Wi-Fi connection is not a revoked device.
        assert service.is_registered is True
        assert service.consecutive_failures == 1

    def test_report_event_never_raises(self, config):
        client = FakeClient(token="t", responses=[AgentApiError("network down")])
        service = self.make(config, client)
        # Called from the shutdown message handler: throwing here would be the last
        # thing this process ever did.
        assert service.report_event("SHUTDOWN") is False

    def test_report_event_sends_a_short_timeout(self, config):
        client = FakeClient(token="t")
        service = self.make(config, client)

        service.report_event("SLEEP")
        _, _, event, timeout = client.calls[-1]
        assert event == "SLEEP"
        assert timeout is not None

    def test_loop_backs_off_after_failures_and_stops_on_request(self, config):
        delays = []
        client = FakeClient(
            token="t",
            responses=[
                AgentApiError("down"),
                AgentApiError("down"),
                {"status": "ONLINE", "config": {}},
            ],
        )
        service = None

        def sleep(seconds):
            delays.append(seconds)
            if len(delays) == 3:
                service.stop()

        service = self.make(config, client, sleep=sleep)
        service.run()

        # Two failures back off 5s then 10s; the recovered beat returns to the interval.
        assert delays == [5, 10, config.heartbeat_interval_seconds]

    def test_first_beat_of_a_run_announces_startup(self, config):
        client = FakeClient(token="t")
        service = None

        def sleep(seconds):
            if len(client.calls) >= 2:
                service.stop()

        service = self.make(config, client, sleep=sleep)
        service.run()

        events = [call[2] for call in client.calls]
        # Exactly once, on the first beat: this is what closes the session the previous
        # run abandoned, and repeating it would close the one we just opened.
        assert events[0] == "STARTUP"
        assert events[1:] == [None]

    def test_startup_is_retried_until_a_beat_actually_lands(self, config):
        client = FakeClient(
            token="t",
            responses=[AgentApiError("down"), {"status": "ONLINE", "config": {}}],
        )
        service = None

        def sleep(seconds):
            if len(client.calls) >= 2:
                service.stop()

        service = self.make(config, client, sleep=sleep)
        service.run()

        # A failed first beat never reached the server, so the announcement is still owed.
        assert [call[2] for call in client.calls] == ["STARTUP", "STARTUP"]

    def test_status_is_reportable_before_anything_has_happened(self, config, queue):
        service = self.make(config, FakeClient(), queue=queue)
        status = service.status()
        assert status["registered"] is False
        assert status["pending_sessions"] == 0
        assert "not enrolled" in status_text(status)

    def test_sync_now_without_enrolment_is_an_error(self, config, queue):
        service = self.make(config, FakeClient(), queue=queue)
        with pytest.raises(NotRegistered):
            service.sync_now()

    def test_sync_now_uploads_everything_pending(self, config, queue):
        client = FakeClient(token="device-token")
        service = self.make(config, client, queue=queue)
        queue.enqueue({"client_event_id": "a", "kind": "APP"})
        queue.enqueue({"client_event_id": "b", "kind": "APP"})

        result = service.sync_now()

        assert result["uploaded"] == 2
        assert result["pending"] == 0
        assert queue.pending_count() == 0

    def test_sync_now_cannot_overlap_the_periodic_loop(self, config, queue):
        """The tray's manual "Sync now" and run_sync's own drain must never run at the
        same time — see the lock in AgentService.__init__ — or each could pull and
        upload the same pending rows."""
        import threading
        import time

        started = threading.Event()
        release = threading.Event()
        order = []

        class SlowClient(FakeClient):
            def sync(self, sessions):
                order.append("periodic-start")
                started.set()
                release.wait(timeout=2)
                order.append("periodic-end")
                return super().sync(sessions)

        client = SlowClient(token="device-token")
        service = self.make(config, client, queue=queue)
        queue.enqueue({"client_event_id": "a", "kind": "APP"})

        periodic = threading.Thread(target=service.run_sync, daemon=True)
        periodic.start()
        assert started.wait(timeout=2), "periodic sync never started"

        # sync_now() must block on the same lock rather than racing in with its own
        # concurrent drain — proven by it only recording its call after the periodic
        # drain (still holding the lock) has released it.
        def manual():
            order.append(service.sync_now())

        manual_thread = threading.Thread(target=manual)
        manual_thread.start()
        time.sleep(0.1)  # give sync_now a chance to wrongly slip in if unlocked
        assert order == ["periodic-start"]

        release.set()
        service.stop()
        periodic.join(timeout=2)
        manual_thread.join(timeout=2)

        assert order[0] == "periodic-start"
        assert order[1] == "periodic-end"


# --- Single instance --------------------------------------------------------


class TestSingleInstance:
    def test_second_instance_is_refused_while_the_first_holds_the_lock(self, tmp_path):
        lock = tmp_path / "agent.lock"
        with SingleInstance(lock), pytest.raises(AlreadyRunning):
            SingleInstance(lock).acquire()

        # Released on exit, so a restart is never blocked by a previous run.
        second = SingleInstance(lock).acquire()
        second.release()

    def test_lock_file_records_the_pid(self, tmp_path):
        import os

        lock = tmp_path / "agent.lock"
        with SingleInstance(lock):
            pass
        # Read after release: Windows refuses reads of a locked byte range even to the
        # process holding it, so "who has the lock?" is answered from the content only
        # once the holder has gone — which is exactly when support needs to ask.
        assert lock.read_text().strip() == str(os.getpid())


# --- Orchestration -----------------------------------------------------------


class TestRunAgent:
    """A tray bug (pystray, Pillow, or tray.py itself) must not take heartbeat, sampling
    and sync down with it — those three loops know nothing about the tray and have no
    reason to die because it did. See main.py's run_agent for the reasoning."""

    def test_a_crashing_tray_falls_back_to_headless_instead_of_killing_the_process(
        self, config, queue
    ):
        import threading

        from agent.main import run_agent

        client = FakeClient(token="test-token")
        service = AgentService(
            config,
            client=client,
            queue=queue,
            idle_reader=lambda: 0,
            token_loader=lambda: "test-token",
            token_saver=lambda value: None,
            token_clearer=lambda: None,
        )

        class CrashingTray:
            def __init__(self, service, on_quit):
                # Real Tray().run() blocks until Quit; standing in for that here means
                # scheduling the same shutdown a real user would eventually trigger,
                # rather than leaving run_agent's fallback stop.wait() blocked forever.
                threading.Timer(0.05, on_quit).start()

            def run(self):
                raise ModuleNotFoundError("No module named 'pystray'")

        import agent.tray

        original_tray = agent.tray.Tray
        agent.tray.Tray = CrashingTray
        try:
            result = run_agent(service, headless=False)
        finally:
            agent.tray.Tray = original_tray

        assert result == 0
        # The heartbeat loop reached at least one beat before shutdown — proof the
        # background threads ran rather than dying alongside the tray.
        assert any(call[0] == "heartbeat" for call in client.calls)

    def test_a_fresh_install_with_no_server_configured_still_starts(self, tmp_path, monkeypatch):
        """The exact scenario that shipped broken: a normal (non-silent) install never
        passes /SERVER=, so this is what autostart runs into on every ordinary install,
        not an edge case. Before the fix, main() raised ConfigError here and exited
        immediately — invisibly, since this is a windowed build with nothing attached to
        print the error to. `main` is exercised directly (not just run_agent) because the
        bug was in load_config, one layer up from what the other test in this class
        covers."""
        import threading

        from agent.main import main

        monkeypatch.setenv("OFFICE_AGENT_DATA_DIR", str(tmp_path))

        class QuittingTray:
            def __init__(self, service, on_quit):
                threading.Timer(0.05, on_quit).start()

            def run(self):
                pass

        import agent.tray

        monkeypatch.setattr(agent.tray, "Tray", QuittingTray)

        result = main([])

        assert result == 0


# --- Tray guard rail -----------------------------------------------------------


class TestTrayGuarded:
    """pystray's own message loop swallows an exception from a menu callback and, on
    it, tears the tray icon down and returns *without re-raising* — from run_agent's
    side that looks identical to a clean exit, so its "tray crashed, keep tracking
    headless" fallback never fires either. A bug in any menu action must not be able to
    take the whole agent down with it; _guarded is what actually prevents that, so it
    gets tested directly rather than trusted by inspection."""

    def test_an_exception_in_a_guarded_callback_never_propagates(self, monkeypatch):
        from agent.tray import _guarded

        monkeypatch.setattr("agent.tray.show_message", lambda *a, **k: None)

        class Something:
            @_guarded
            def broken(self):
                raise RuntimeError("boom")

        Something().broken()  # must not raise

    def test_the_exception_is_logged_rather_than_lost(self, monkeypatch, caplog):
        from agent.tray import _guarded

        monkeypatch.setattr("agent.tray.show_message", lambda *a, **k: None)

        class Something:
            @_guarded
            def broken(self):
                raise RuntimeError("boom")

        with caplog.at_level("ERROR"):
            Something().broken()

        assert "broken" in caplog.text
        assert "boom" in caplog.text

    def test_a_failure_in_the_error_dialog_itself_is_also_swallowed(self, monkeypatch):
        """show_message is exactly what a broken tkinter/Tcl install would take down
        with it — the one thing worse than the original action failing silently is the
        attempt to *report* that failure also crashing the tray."""
        from agent.tray import _guarded

        monkeypatch.setattr(
            "agent.tray.show_message",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("tkinter is broken too")),
        )

        class Something:
            @_guarded
            def broken(self):
                raise RuntimeError("boom")

        Something().broken()  # must not raise, even though show_message also raises
