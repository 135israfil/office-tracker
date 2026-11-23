"""Startup, shutdown, sleep, wake, lock and unlock (§13, §34 System Collector).

Windows announces these through window messages, so the agent keeps one hidden,
message-only window whose entire job is to translate them into lifecycle events.

The important one is `WM_QUERYENDSESSION`. Windows sends it *before* it starts killing
processes, which is the only moment a shutdown can still be reported. The handler must
answer immediately and must never block: refusing to return promptly gets the process
terminated anyway, and the user gets a "this app is preventing shutdown" dialog.

Even so, a reported shutdown is a best-effort nicety. Power cuts, crashes and pulled
plugs send nothing at all, which is why the server closes open sessions by inference —
see `computers/services.py`. This collector reduces how often that inference is needed;
it is not what makes the data correct.
"""

from __future__ import annotations

import contextlib
import logging
import sys
import threading

log = logging.getLogger(__name__)

# Window message constants. Spelled out rather than imported from win32con so this
# module can be read, and tested, on any platform.
WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016
WM_POWERBROADCAST = 0x0218
WM_WTSSESSION_CHANGE = 0x02B1

PBT_APMSUSPEND = 0x0004
PBT_APMRESUMESUSPEND = 0x0007
PBT_APMRESUMEAUTOMATIC = 0x0012

WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8
NOTIFY_FOR_THIS_SESSION = 0

EVENT_STARTUP = "STARTUP"
EVENT_SHUTDOWN = "SHUTDOWN"
EVENT_SLEEP = "SLEEP"
EVENT_WAKE = "WAKE"
EVENT_LOCK = "LOCK"
EVENT_UNLOCK = "UNLOCK"

# macOS notification names this watcher listens for. NSWorkspace's own notification
# center carries power events; screen lock/unlock is only ever announced on the
# *distributed* notification center, which is why _run_macos below registers with two
# different centers rather than one.
MACOS_WORKSPACE_EVENTS = {
    "NSWorkspaceWillPowerOffNotification": EVENT_SHUTDOWN,
    "NSWorkspaceWillSleepNotification": EVENT_SLEEP,
    "NSWorkspaceDidWakeNotification": EVENT_WAKE,
}
MACOS_DISTRIBUTED_EVENTS = {
    "com.apple.screenIsLocked": EVENT_LOCK,
    "com.apple.screenIsUnlocked": EVENT_UNLOCK,
}


def lifecycle_event_macos(notification_name: str) -> str | None:
    """Translate one macOS notification name into a lifecycle event, or None.

    Pure, same reason as lifecycle_event above: every branch is testable without a
    real NSWorkspace/NSDistributedNotificationCenter.
    """
    if notification_name in MACOS_WORKSPACE_EVENTS:
        return MACOS_WORKSPACE_EVENTS[notification_name]
    return MACOS_DISTRIBUTED_EVENTS.get(notification_name)


def lifecycle_event(message: int, wparam: int) -> str | None:
    """Translate one window message into a lifecycle event, or None if it is not one.

    Pure, so every branch is testable without Windows — which matters because the real
    handler runs inside a message loop during shutdown, the least debuggable moment in
    the life of the process.
    """
    if message == WM_QUERYENDSESSION:
        return EVENT_SHUTDOWN
    if message == WM_POWERBROADCAST:
        if wparam == PBT_APMSUSPEND:
            return EVENT_SLEEP
        if wparam in (PBT_APMRESUMESUSPEND, PBT_APMRESUMEAUTOMATIC):
            return EVENT_WAKE
        return None
    if message == WM_WTSSESSION_CHANGE:
        if wparam == WTS_SESSION_LOCK:
            return EVENT_LOCK
        if wparam == WTS_SESSION_UNLOCK:
            return EVENT_UNLOCK
    return None


class SystemEventWatcher:
    """Runs a message-only window on its own thread and calls back with events.

    The callback is invoked on the message-pump thread. It must be quick — the shutdown
    path is on a stopwatch — so callers send one short-timeout request and return.
    """

    def __init__(self, callback):
        self.callback = callback
        self._thread = None
        self._hwnd = None
        self._stop = threading.Event()

    @property
    def supported(self) -> bool:
        return sys.platform in ("win32", "darwin")

    def start(self):
        if not self.supported:
            log.info("System event watcher not started: unsupported platform.")
            return False
        target = self._run_macos if sys.platform == "darwin" else self._run
        self._thread = threading.Thread(target=target, name="system-events", daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        if self._hwnd is not None:  # pragma: no cover - requires a real window
            try:
                import win32con
                import win32gui

                win32gui.PostMessage(self._hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception as exc:
                log.debug("Could not post WM_CLOSE: %s", exc)
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _emit(self, event):
        try:
            self.callback(event)
        except Exception:
            # A failure to report must never take down the message pump: the next
            # message could be the shutdown notice.
            log.exception("Lifecycle callback failed for %s", event)

    def _run(self):  # pragma: no cover - requires a Windows message pump
        try:
            import win32api
            import win32con
            import win32gui
            import win32ts
        except ImportError as exc:
            # A packaging mistake must degrade, not crash: without pywin32 the agent
            # simply stops reporting lifecycle events, and the server keeps inferring
            # shutdowns from missed heartbeats exactly as it does after a power cut.
            log.error("Lifecycle events unavailable (pywin32 missing): %s", exc)
            return

        def handler(hwnd, message, wparam, lparam):
            event = lifecycle_event(message, wparam)
            if event:
                self._emit(event)
            if message == WM_QUERYENDSESSION:
                # True means "I am not blocking the shutdown". Anything else fights the
                # user, which is not the agent's place.
                return True
            if message in (WM_ENDSESSION, win32con.WM_CLOSE):
                win32gui.PostQuitMessage(0)
            return True

        wndclass = win32gui.WNDCLASS()
        wndclass.lpszClassName = "OfficeTrackerAgentEvents"
        wndclass.hInstance = win32api.GetModuleHandle(None)
        wndclass.lpfnWndProc = {
            WM_QUERYENDSESSION: handler,
            WM_ENDSESSION: handler,
            WM_POWERBROADCAST: handler,
            WM_WTSSESSION_CHANGE: handler,
            win32con.WM_CLOSE: handler,
            win32con.WM_DESTROY: handler,
        }

        try:
            atom = win32gui.RegisterClass(wndclass)
            self._hwnd = win32gui.CreateWindow(
                atom, "OfficeTrackerAgent", 0, 0, 0, 0, 0, 0, 0, wndclass.hInstance, None
            )
            # Lock/unlock notifications are opt-in; without this the window never hears
            # about them. Failure is not fatal — §34 asks for lock "where practical".
            try:
                win32ts.WTSRegisterSessionNotification(self._hwnd, NOTIFY_FOR_THIS_SESSION)
            except Exception as exc:
                log.warning("Session lock notifications unavailable: %s", exc)

            # STARTUP is deliberately *not* emitted here. It is a fact about this
            # process, not a window message, and racing it against the heartbeat
            # thread meant the server could see a plain heartbeat first — which
            # refreshes "last seen" and makes the previous run's abandoned session
            # swallow the downtime it was supposed to be closed before. The service
            # sends STARTUP as its first heartbeat instead, where the ordering is
            # guaranteed.
            while not self._stop.is_set():
                win32gui.PumpWaitingMessages()
                self._stop.wait(0.5)
        except Exception:
            log.exception("System event watcher stopped")
        finally:
            if self._hwnd is not None:
                # Tearing down a window that Windows has already taken away is normal
                # during shutdown, and there is nothing useful left to do about it.
                with contextlib.suppress(Exception):
                    win32ts.WTSUnRegisterSessionNotification(self._hwnd)
                with contextlib.suppress(Exception):
                    win32gui.DestroyWindow(self._hwnd)
                self._hwnd = None

    def _run_macos(self):  # pragma: no cover - requires a real macOS session
        try:
            from AppKit import NSWorkspace
            from Foundation import NSDate, NSDistributedNotificationCenter, NSRunLoop
        except ImportError as exc:
            # Same degrade-not-crash contract as the Windows pywin32-missing path: the
            # server keeps inferring shutdowns from missed heartbeats either way.
            log.error("Lifecycle events unavailable (pyobjc missing): %s", exc)
            return

        # (center, observer) pairs, so teardown removes each observer from the same
        # center that registered it rather than guessing.
        registrations = []

        def make_handler(event):
            def handler(_notification):
                self._emit(event)

            return handler

        workspace_center = NSWorkspace.sharedWorkspace().notificationCenter()
        for name, event in MACOS_WORKSPACE_EVENTS.items():
            observer = workspace_center.addObserverForName_object_queue_usingBlock_(
                name, None, None, make_handler(event)
            )
            registrations.append((workspace_center, observer))

        # Lock/unlock is never announced on NSWorkspace's own center — only on the
        # distributed one, which is why this is a second registration against a
        # different object entirely rather than two more entries in the loop above.
        distributed_center = NSDistributedNotificationCenter.defaultCenter()
        for name, event in MACOS_DISTRIBUTED_EVENTS.items():
            observer = distributed_center.addObserverForName_object_queue_usingBlock_(
                name, None, None, make_handler(event)
            )
            registrations.append((distributed_center, observer))

        try:
            run_loop = NSRunLoop.currentRunLoop()
            while not self._stop.is_set():
                run_loop.runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.5))
        except Exception:
            log.exception("System event watcher stopped")
        finally:
            for center, observer in registrations:
                with contextlib.suppress(Exception):
                    center.removeObserver_(observer)
