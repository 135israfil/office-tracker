"""macOS LaunchAgent autostart (the write half of what tests/test_cleanup.py's
`_remove_launch_agent` tests already cover the removal of).
"""

from __future__ import annotations

import pytest

from agent import autostart


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A fake home directory so the plist never touches a real one."""
    monkeypatch.setattr(autostart.Path, "home", lambda: tmp_path)
    return tmp_path


class TestEnsureInstalled:
    def test_skips_on_non_macos_platforms(self, home, monkeypatch):
        monkeypatch.setattr(autostart.sys, "platform", "win32")
        monkeypatch.setattr(autostart.sys, "frozen", True, raising=False)

        assert autostart.ensure_installed() == "skipped (not macOS)"
        assert not autostart.launch_agent_path().exists()

    def test_skips_a_dev_run_that_is_not_a_frozen_build(self, home, monkeypatch):
        """Writing an autostart entry pointing at a bare `python` interpreter would
        silently break at the next login rather than relaunch the agent."""
        monkeypatch.setattr(autostart.sys, "platform", "darwin")
        monkeypatch.setattr(autostart.sys, "frozen", False, raising=False)

        assert autostart.ensure_installed() == "skipped (not a frozen build)"
        assert not autostart.launch_agent_path().exists()

    def test_writes_the_plist_pointing_at_the_running_executable(self, home, monkeypatch):
        monkeypatch.setattr(autostart.sys, "platform", "darwin")
        monkeypatch.setattr(autostart.sys, "frozen", True, raising=False)
        monkeypatch.setattr(autostart.sys, "executable", "/Applications/OfficeTrackerAgent.app/Contents/MacOS/OfficeTrackerAgent")
        calls = []
        monkeypatch.setattr(
            "subprocess.run", lambda *a, **k: calls.append(a[0]) or None
        )

        result = autostart.ensure_installed()

        assert result == "installed"
        path = autostart.launch_agent_path()
        assert path.exists()
        contents = path.read_text(encoding="utf-8")
        assert "/Applications/OfficeTrackerAgent.app/Contents/MacOS/OfficeTrackerAgent" in contents
        assert autostart.LAUNCH_AGENT_LABEL in contents
        # Activated for the current session too, not just the next login.
        assert calls == [["/bin/launchctl", "load", "-w", str(path)]]

    def test_an_already_correct_plist_is_left_alone(self, home, monkeypatch):
        monkeypatch.setattr(autostart.sys, "platform", "darwin")
        monkeypatch.setattr(autostart.sys, "frozen", True, raising=False)
        monkeypatch.setattr(autostart.sys, "executable", "/Applications/OfficeTrackerAgent.app/Contents/MacOS/OfficeTrackerAgent")
        calls = []
        monkeypatch.setattr(
            "subprocess.run", lambda *a, **k: calls.append(a[0]) or None
        )

        first = autostart.ensure_installed()
        assert first == "installed"

        second = autostart.ensure_installed()

        assert second == "already installed"
        # Only the first call actually touched launchctl.
        assert len(calls) == 1

    def test_a_moved_app_gets_its_plist_repaired(self, home, monkeypatch):
        monkeypatch.setattr(autostart.sys, "platform", "darwin")
        monkeypatch.setattr(autostart.sys, "frozen", True, raising=False)
        monkeypatch.setattr("subprocess.run", lambda *a, **k: None)

        monkeypatch.setattr(autostart.sys, "executable", "/Applications/OfficeTrackerAgent.app/Contents/MacOS/OfficeTrackerAgent")
        autostart.ensure_installed()

        monkeypatch.setattr(autostart.sys, "executable", "/Users/alice/Applications/OfficeTrackerAgent.app/Contents/MacOS/OfficeTrackerAgent")
        result = autostart.ensure_installed()

        assert result == "installed"
        assert "/Users/alice/Applications" in autostart.launch_agent_path().read_text(encoding="utf-8")

    def test_a_write_failure_is_reported_rather_than_raised(self, home, monkeypatch):
        monkeypatch.setattr(autostart.sys, "platform", "darwin")
        monkeypatch.setattr(autostart.sys, "frozen", True, raising=False)
        monkeypatch.setattr(autostart.sys, "executable", "/Applications/OfficeTrackerAgent.app/Contents/MacOS/OfficeTrackerAgent")

        def boom(*_a, **_k):
            raise OSError("disk full")

        monkeypatch.setattr(autostart.Path, "write_text", boom)

        assert autostart.ensure_installed().startswith("failed:")


class TestPlistContents:
    def test_contains_the_executable_and_label(self):
        xml = autostart.plist_contents("/path/to/OfficeTrackerAgent")

        assert "/path/to/OfficeTrackerAgent" in xml
        assert autostart.LAUNCH_AGENT_LABEL in xml
        assert "<key>RunAtLoad</key>" in xml
        assert "<true/>" in xml
