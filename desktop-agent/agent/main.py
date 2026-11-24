"""Agent entry point: CLI, lifecycle wiring and the tray loop.

Typical use, in the order a machine goes through them:

    python -m agent --server https://office.example.com --enroll ABCDE-FGHJK
    python -m agent                 # tray app, what autostart runs
    python -m agent --status        # what support asks for first
    python -m agent --headless      # no tray; for a test box or a smoke check
    python -m agent --uninstall-cleanup   # what the uninstaller runs

The heartbeat runs on its own thread so the tray stays responsive, and the system-event
watcher runs on a third so a shutdown notice is never queued behind a slow request.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import signal
import sys
import threading

from .api import AgentApiError, normalise_server_url
from .collectors.system import SystemEventWatcher
from .config import AgentConfig, ConfigError, TokenStorageError, data_dir
from .service import AgentService
from .single_instance import AlreadyRunning, SingleInstance
from .version import __version__

log = logging.getLogger("agent")


def configure_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    handlers = [logging.StreamHandler()]
    # The windowed build has no console for the StreamHandler above to reach, which
    # means every log line — including an exception from a tray menu callback, which
    # pystray's win32 backend swallows rather than crashing the icon on — was
    # previously going nowhere anyone could see. cleanup.py has removed this exact
    # file on uninstall since Phase 9; nothing ever actually wrote it until now.
    try:
        from logging.handlers import RotatingFileHandler

        log_dir = data_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                log_dir / "agent.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8"
            )
        )
    except OSError:
        # Best-effort: a machine where the data directory cannot be created or written
        # has bigger problems than a missing log file, and this must never be why the
        # agent fails to start.
        pass

    for handler in handlers:
        handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    for handler in handlers:
        root.addHandler(handler)


def build_parser():
    parser = argparse.ArgumentParser(prog="agent", description="OneRoof Task Manager desktop agent")
    parser.add_argument("--server", help="Backend URL, e.g. https://office.example.com")
    parser.add_argument("--enroll", metavar="CODE", help="Register this PC with an enrollment code")
    parser.add_argument("--status", action="store_true", help="Print agent status and exit")
    parser.add_argument("--headless", action="store_true", help="Run without a tray icon")
    parser.add_argument("--verbose", action="store_true", help="Debug logging")
    # Run by the uninstaller in the logged-in user's context: the device token lives in
    # that user's Credential Manager, which an elevated uninstaller cannot see.
    parser.add_argument(
        "--uninstall-cleanup",
        action="store_true",
        help="Remove the local queue, config and stored device token, then exit.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def load_config(server: str | None) -> AgentConfig:
    """Load persisted config, applying --server if given.

    Deliberately does not require server_url to be set: a normal (non-silent) install
    never passes /SERVER=, so a freshly installed machine reaching this with nothing
    configured yet is the common case, not an error. AgentService and AgentClient both
    tolerate an empty server_url — every network call fails with a clear AgentApiError
    instead, which the tray and the heartbeat/sync loops already know how to handle (see
    the "not enrolled yet" warning below and AgentClient._url). The alternative, raising
    here, would mean the tray autostart runs and silently exits every single time on a
    machine nobody has configured yet — invisible, since this is a windowed build with no
    console to print to.
    """
    config = AgentConfig.load()
    if server:
        config.server_url = normalise_server_url(server)
        config.save()
    return config


def run_agent(service: AgentService, headless: bool) -> int:
    """Wire the threads together and block until something asks us to stop."""
    stop = threading.Event()

    def shutdown(*_):
        service.stop()
        stop.set()
        if not headless and sys.platform == "darwin":
            # On macOS the tray's dialog loop, not this function's own stop.wait(),
            # is what's actually blocking the thread below (see tray.py's _UiThread) —
            # a signal alone stops the background loops but leaves that blocked, so
            # the process would hang instead of exiting. A no-op before the tray
            # exists yet or on any other platform.
            from .tray import stop_ui_thread

            stop_ui_thread()

    # Ctrl+C and a service stop both arrive as signals; without this the process would
    # die mid-heartbeat instead of closing down cleanly.
    for sig in (signal.SIGINT, signal.SIGTERM):
        # Only the main thread may install handlers; anywhere else this is a no-op.
        with contextlib.suppress(ValueError, OSError):
            signal.signal(sig, shutdown)

    watcher = SystemEventWatcher(service.report_event)
    watcher.start()

    # Four independent loops (see AgentService): an outage must not stop collection,
    # and a stuck collector must not stop liveness.
    threads = [
        threading.Thread(target=service.run, name="heartbeat", daemon=True),
        threading.Thread(target=service.run_sampler, name="sampler", daemon=True),
        threading.Thread(target=service.run_sync, name="sync", daemon=True),
        threading.Thread(target=service.run_screenshots, name="screenshots", daemon=True),
    ]
    for thread in threads:
        thread.start()

    try:
        if headless:
            stop.wait()
        else:
            from .tray import Tray

            try:
                Tray(service, on_quit=shutdown).run()
            except Exception:
                # The tray is UI glue around three loops that do not depend on it: a bug
                # in pystray, Pillow or the tray code itself must not take heartbeat,
                # sampling and sync down with it. Fall back to running headless rather
                # than letting the process die — tracking staying up matters more than
                # the icon, and a silent gap here is exactly the kind of failure nobody
                # is watching for (see the module docstring in service.py).
                log.exception("Tray failed; continuing headless")
                stop.wait()
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        shutdown()
    finally:
        service.stop()
        # Close and upload what is still open before announcing the shutdown, so the
        # last minutes of the day are not left sitting in the local queue.
        service.final_sync()
        # Best effort: tell the server we are going before it has to infer it.
        service.report_event("SHUTDOWN")
        watcher.stop()
        for thread in threads:
            thread.join(timeout=5)
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(args.verbose)

    if args.uninstall_cleanup:
        # Before load_config: an uninstall must work on a machine that was never
        # enrolled, where there is no server URL to complain about.
        from .cleanup import cleanup

        result = cleanup()
        for name, outcome in result["actions"].items():
            print(f"{name}: {outcome}")
        return 0

    try:
        config = load_config(args.server)
    except (ConfigError, ValueError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    service = AgentService(config)

    if args.enroll:
        try:
            service.enroll(args.enroll)
        except (AgentApiError, TokenStorageError) as exc:
            print(f"Enrolment failed: {exc}", file=sys.stderr)
            return 1
        print(f"Enrolled as {config.computer_name}.")
        if args.status:
            print(json.dumps(service.status(), indent=2))
        return 0

    if args.status:
        print(json.dumps(service.status(), indent=2))
        return 0

    if not config.is_configured:
        # Same reasoning as the "not enrolled" branch below, one step earlier: a normal
        # (non-silent) install never passes /SERVER=, so this is the ordinary state of a
        # freshly installed machine, not a misconfiguration. See load_config.
        log.warning("No server URL configured yet. Run with --server URL once.")
    elif not service.is_registered:
        # Not an error: a freshly installed PC sits here, tray icon amber, until someone
        # types the code. Exiting instead would mean autostart silently does nothing.
        log.warning("This computer is not enrolled yet. Use --enroll CODE or the tray menu.")

    try:
        with SingleInstance():
            return run_agent(service, headless=args.headless)
    except AlreadyRunning as exc:
        # Two agents would double every heartbeat and every session.
        print(str(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
