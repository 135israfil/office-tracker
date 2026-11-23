"""Uninstall cleanup (Phase 9).

The queue file is a record of which applications and websites somebody used. Leaving it
on a machine that is no longer tracked is a privacy failure under §31, not an untidy
uninstall — so what the uninstaller removes, and what it refuses to remove, is tested
rather than trusted to a script nobody runs until the day it matters.
"""

from __future__ import annotations

import json

import pytest

from agent.cleanup import REMOVABLE_FILES, cleanup
from agent.main import main


@pytest.fixture
def install(tmp_path, monkeypatch):
    """A data directory that looks like a used installation."""
    monkeypatch.setenv("OFFICE_AGENT_DATA_DIR", str(tmp_path))

    (tmp_path / "queue.sqlite3").write_bytes(b"sqlite queue with a day of history")
    (tmp_path / "queue.sqlite3-wal").write_bytes(b"write-ahead log")
    (tmp_path / "screenshots.sqlite3").write_bytes(b"sqlite queue of captured screenshots")
    (tmp_path / "screenshots.sqlite3-wal").write_bytes(b"write-ahead log")
    (tmp_path / "agent.json").write_text(json.dumps({"server_url": "https://office.example.com"}))
    (tmp_path / "agent.lock").write_text("")
    (tmp_path / "agent.log").write_text("some log lines")

    # The token lives in Credential Manager, not on disk. Cleanup must ask the keyring
    # to drop it, so the test watches for that rather than for a file.
    cleared = []
    monkeypatch.setattr("agent.cleanup.clear_token", lambda: cleared.append(True))
    return tmp_path, cleared


class TestCleanup:
    def test_the_queue_is_removed(self, install):
        directory, _ = install

        cleanup()

        assert not (directory / "queue.sqlite3").exists()
        assert not (directory / "queue.sqlite3-wal").exists()

    def test_the_screenshot_queue_is_removed(self, install):
        """Otherwise a decommissioned PC keeps a file of actual screen captures (§31)."""
        directory, _ = install

        cleanup()

        assert not (directory / "screenshots.sqlite3").exists()
        assert not (directory / "screenshots.sqlite3-wal").exists()

    def test_config_lock_and_log_are_removed(self, install):
        directory, _ = install

        cleanup()

        for name in ("agent.json", "agent.lock", "agent.log"):
            assert not (directory / name).exists(), name

    def test_the_autostart_entry_is_removed(self, install, monkeypatch):
        """Otherwise the agent comes back at the next login pointing at a deleted exe."""
        calls = []
        monkeypatch.setattr(
            "agent.cleanup._remove_autostart", lambda: calls.append(True) or "removed"
        )

        result = cleanup()

        assert calls == [True]
        assert result["actions"]["autostart"] == "removed"

    def test_on_macos_the_autostart_entry_removal_dispatches_to_the_launch_agent(
        self, install, monkeypatch
    ):
        """On macOS there is no Run key or Scheduled Task to remove - the equivalent
        is a LaunchAgent plist, and cleanup must reach for that one instead."""
        monkeypatch.setattr("agent.cleanup.sys.platform", "darwin")
        calls = []
        monkeypatch.setattr(
            "agent.cleanup._remove_launch_agent", lambda: calls.append(True) or "removed"
        )
        monkeypatch.setattr(
            "agent.cleanup._remove_run_key", lambda: (_ for _ in ()).throw(AssertionError())
        )
        monkeypatch.setattr(
            "agent.cleanup._remove_scheduled_task",
            lambda: (_ for _ in ()).throw(AssertionError()),
        )

        result = cleanup()

        assert calls == [True]
        assert result["actions"]["autostart"] == "removed"

    def test_the_device_token_is_cleared_from_the_credential_store(self, install):
        _, cleared = install

        result = cleanup()

        assert cleared == [True]
        assert result["actions"]["device_token"] == "cleared"

    def test_the_data_directory_goes_when_it_is_empty(self, install):
        directory, _ = install

        result = cleanup()

        assert not directory.exists()
        assert result["actions"]["data_directory"] == "removed"

    def test_a_file_that_is_not_ours_is_left_alone_and_so_is_its_directory(self, install):
        """`%PROGRAMDATA%\\OfficeTracker` is ours by convention, not by guarantee. A
        wildcard delete there is one packaging mistake away from taking something else."""
        directory, _ = install
        stranger = directory / "something-else.txt"
        stranger.write_text("not ours")

        result = cleanup()

        assert stranger.exists()
        assert directory.exists()
        assert result["actions"]["data_directory"] == "kept (not empty)"

    def test_a_dry_run_removes_nothing(self, install):
        directory, cleared = install

        result = cleanup(dry_run=True)

        assert (directory / "queue.sqlite3").exists()
        assert (directory / "agent.json").exists()
        assert cleared == []
        assert result["actions"]["queue.sqlite3"] == "would remove"

    def test_cleaning_a_machine_that_was_never_enrolled_is_not_an_error(
        self, tmp_path, monkeypatch
    ):
        """The common case in a botched rollout: install, never enrol, uninstall."""
        monkeypatch.setenv("OFFICE_AGENT_DATA_DIR", str(tmp_path / "never-created"))
        monkeypatch.setattr("agent.cleanup.clear_token", lambda: None)

        result = cleanup()

        assert all(
            outcome == "absent"
            for name, outcome in result["actions"].items()
            if name in REMOVABLE_FILES
        )

    def test_a_locked_file_is_reported_rather_than_raising(self, install, monkeypatch):
        """An uninstall must not fail with a dialog because one file was held open."""
        directory, _ = install

        real_unlink = type(directory).unlink

        def stubborn(self, *args, **kwargs):
            if self.name == "queue.sqlite3":
                raise PermissionError("file is in use by another process")
            return real_unlink(self, *args, **kwargs)

        monkeypatch.setattr(type(directory), "unlink", stubborn)

        result = cleanup()

        assert "failed" in result["actions"]["queue.sqlite3"]
        # Everything else still went.
        assert not (directory / "agent.json").exists()


class TestCleanupCommand:
    def test_the_flag_runs_cleanup_and_exits_zero(self, install, capsys):
        directory, cleared = install

        assert main(["--uninstall-cleanup"]) == 0

        assert not (directory / "queue.sqlite3").exists()
        assert cleared == [True]
        assert "queue.sqlite3" in capsys.readouterr().out

    def test_it_works_without_a_configured_server(self, tmp_path, monkeypatch, capsys):
        """Uninstall runs on machines that were never configured, and must not stop at
        the "no server URL" error the normal startup path raises."""
        monkeypatch.setenv("OFFICE_AGENT_DATA_DIR", str(tmp_path))
        monkeypatch.setattr("agent.cleanup.clear_token", lambda: None)

        assert main(["--uninstall-cleanup"]) == 0
