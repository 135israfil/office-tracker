"""Tray icon and the small dialogs around it (D3).

The agent is a visible tray app, not a hidden service, and that was a deliberate choice:
Session 0 isolation makes idle and foreground detection impossible from a service, and
§31's spirit is that people know tracking is on. The icon is the reminder.

This module is UI glue. Everything it can decide is decided in `AgentService`; if you
find yourself adding a rule here, it belongs there instead.
"""

from __future__ import annotations

import contextlib
import functools
import logging
import queue
import sys
import threading

log = logging.getLogger(__name__)


def _guarded(func):
    """Menu-callback safety net.

    pystray's win32 backend runs its whole message loop under one bare `except`, and on
    any exception from a callback it logs to its own internal logger, destroys the tray
    icon, and returns *normally* — no re-raise. From run_agent's point of view that
    looks like the tray exited cleanly, so its own "tray crashed, fall back to
    headless" handling never fires either: an unhandled exception here does not just
    fail silently, it takes the whole tray down and, with it, the whole agent process,
    since nothing downstream ever sees a failure to react to. Catching it here, before
    it ever reaches pystray's loop, is what actually keeps the agent running.
    """

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except Exception:
            log.exception("Tray action %r failed", func.__name__)
            with contextlib.suppress(Exception):
                show_message(
                    "Office Tracker",
                    "Something went wrong and this action didn't complete.\n"
                    "See agent.log for details.",
                )

    return wrapper


# Icon colours by state, in the order a glance reads them: green running, amber waiting
# to be enrolled, red cannot reach the server.
COLOURS = {
    "running": (34, 139, 76),
    "unenrolled": (217, 149, 20),
    "error": (185, 28, 28),
}


def _icon_image(colour):
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((6, 6, 58, 58), fill=colour)
    return image


def status_text(status: dict) -> str:
    """The status blurb, kept plain enough to read out over a support call."""
    lines = [
        f"Office Tracker agent {status['version']}",
        f"Server: {status['server_url'] or 'not configured'}",
    ]
    if status["registered"]:
        lines.append(f"Computer: {status['computer_name']}")
        lines.append(f"Employee: {status['employee_name'] or 'unknown'}")
        lines.append(f"State: {status['state'] or 'starting'}")
        lines.append("Collecting: yes" if status["collecting"] else "Collecting: paused by admin")
        lines.append(
            "Screenshots: on" if status["screenshot_capture_enabled"] else "Screenshots: off"
        )
    else:
        lines.append("This computer is not enrolled yet.")
    if status["last_error"]:
        lines.append(f"Last error: {status['last_error']}")
    return "\n".join(lines)


def _raise_above_everything(window):
    """Centre a Toplevel on screen and force it to the foreground.

    A window created fresh from the tray's background process is subject to the same
    Windows foreground-lock that pystray's own popup menu needs SetForegroundWindow to
    get past (see Tray._on_notify's win32 backend) — except nothing forces that for a
    plain dialog, so it can open successfully and just sit behind whatever window
    already had focus. That reads as "I clicked Enrol and nothing happened" when what
    actually happened is the prompt opened invisibly.

    This has to run on the dialog itself, not a parent it was built from: tkinter's
    stdlib simpledialog/messagebox each create their own internal Toplevel that does
    not inherit -topmost from a withdrawn root the way it looks like it should — which
    is why the earlier fix (setting it on the root) still left the dialog invisible on
    a real machine. Building the dialog directly, as the callers below now do, means
    there is always a concrete window to apply this to.

    -topmost/lift()/focus_force() alone are not enough on real Windows machines: they
    control z-order and Tk's own idea of which widget is focused (real enough to blink a
    text cursor) without making Windows hand this background process actual OS keyboard
    focus — the window sits on top, looking active, while every keystroke and paste goes
    to whatever window genuinely has focus. AllowSetForegroundWindow was tried here first
    and dropped: it only works when called by a process that already holds foreground-
    delegation rights, which a tray-triggered background process does not have, so it was
    a silent no-op. Restoring a minimized window is different — it is one of the state
    transitions Windows explicitly lets any process use to reclaim real foreground focus,
    no delegated permission and no synthetic input event required, which is also why it
    does not carry the AV/EDR suspicion that ruled out AttachThreadInput-style tricks for
    the tray menu itself (see OfficeTracker.iss's note on the Scheduled Task revert).
    """
    window.update_idletasks()
    width, height = window.winfo_width(), window.winfo_height()
    x = (window.winfo_screenwidth() - width) // 2
    y = (window.winfo_screenheight() - height) // 2
    window.geometry(f"{width}x{height}+{x}+{y}")
    window.deiconify()
    if sys.platform == "win32":
        # The iconify/deiconify dance below is a Windows-specific foreground-lock
        # workaround (see the module docstring above) — unverified whether macOS
        # needs it too, so it stays off there rather than risking a window that opens
        # in a transient iconified state on a desktop with no foreground lock to work
        # around in the first place.
        window.update()
        window.iconify()
        window.update()
        window.deiconify()
    window.attributes("-topmost", True)
    window.lift()
    # grab_set() (called next, by both callers) needs the window to already be viewable —
    # actually mapped on screen by the window manager — or it raises TclError: "grab
    # failed: another application has grab", a misleading message for what is really a
    # race between this call returning and the WM finishing the map. deiconify() only
    # requests mapping; it does not wait for it. wait_visibility() blocks until Tk
    # reports the window viewable, which is what makes the grab_set() right after this
    # call reliable rather than a startup-timing gamble.
    window.wait_visibility()
    # focus_force() has to come after wait_visibility(), not before: forcing OS focus onto
    # a window that is not mapped yet is a no-op Windows silently drops, which is why the
    # window could show up genuinely topmost and still never receive a keystroke.
    window.focus_force()


class _UiThread:
    """The one thread that ever touches Tkinter, with one persistent interpreter.

    prompt_for_code/_show_status/_enroll used to each create and destroy their own
    tk.Tk() wherever they happened to be called from — which, for the tray menu, is
    synchronously inside pystray's own native Win32 message loop, on pystray's own
    thread. Two toolkits each running their own message pump on the same thread is
    fragile: the dialog could end up genuinely active per Windows (real coloured title
    bar, blinking text cursor) while neither keystrokes nor button clicks ever reached a
    widget, because pystray's loop — not Tk's — was still the one pumping that thread's
    messages. Giving Tk one dedicated thread with its own mainloop() running
    continuously, and marshalling every dialog onto it through a thread-safe queue
    (`run`, below), removes the conflict entirely: Tk's event loop is never nested
    inside a foreign one, only ever inside itself, which is the normal and fully
    supported way a modal dialog's own wait_window() has always worked.
    """

    def __init__(self):
        self.root = None
        self._queue = queue.Queue()
        ready = threading.Event()
        threading.Thread(target=self._run, args=(ready,), name="tray-ui", daemon=True).start()
        ready.wait()

    def _run(self, ready):
        import tkinter as tk

        self.root = tk.Tk()
        self.root.withdraw()
        self._poll()
        ready.set()
        self.root.mainloop()

    def _poll(self):
        # Runs only on this thread: the first call from _run, and every later one
        # scheduled via root.after from inside this same method. That is what makes it
        # safe to run arbitrary builder() callbacks here — nothing outside this thread
        # ever touches Tk directly, it only ever hands work to the queue below.
        while True:
            try:
                task = self._queue.get_nowait()
            except queue.Empty:
                break
            task()
        self.root.after(30, self._poll)

    def run(self, builder):
        """Run builder(root) on the UI thread; block the caller until it returns."""
        result = []
        error = []
        done = threading.Event()

        def task():
            try:
                result.append(builder(self.root))
            except Exception as exc:  # noqa: BLE001 - re-raised on the caller's thread below
                error.append(exc)
            finally:
                done.set()

        self._queue.put(task)
        done.wait()
        if error:
            raise error[0]
        return result[0]


_ui_thread = None
_ui_thread_lock = threading.Lock()


def _ui() -> _UiThread:
    global _ui_thread
    with _ui_thread_lock:
        if _ui_thread is None:
            _ui_thread = _UiThread()
    return _ui_thread


def prompt_for_code(parent_title="Office Tracker") -> str | None:
    """Ask for an enrollment code with a small hand-built dialog.

    Not tkinter.simpledialog: see _raise_above_everything for why that stopped being
    reliable. tkinter itself rather than Qt or wx — one small dialog, used once per
    machine, is not worth thirty megabytes in the installer.
    """

    def build(root):
        import tkinter as tk

        dialog = tk.Toplevel(root)
        dialog.title(parent_title)
        dialog.resizable(False, False)

        tk.Label(dialog, text="Enter the enrollment code from your administrator:").pack(
            padx=16, pady=(16, 8)
        )
        entry = tk.Entry(dialog, width=32)
        entry.pack(padx=16, pady=(0, 8))

        result = {"code": None}

        def submit(*_):
            result["code"] = entry.get().strip() or None
            dialog.destroy()

        def cancel(*_):
            dialog.destroy()

        buttons = tk.Frame(dialog)
        buttons.pack(pady=(0, 16))
        tk.Button(buttons, text="OK", command=submit, width=10, default="active").pack(
            side="left", padx=4
        )
        tk.Button(buttons, text="Cancel", command=cancel, width=10).pack(side="left", padx=4)

        dialog.bind("<Return>", submit)
        dialog.bind("<Escape>", cancel)
        dialog.protocol("WM_DELETE_WINDOW", cancel)

        try:
            _raise_above_everything(dialog)
            # Only now, with the window genuinely visible and holding real OS focus, does
            # setting focus on the entry actually stick — doing this earlier (as it used
            # to) set Tk's internal focus record on a widget in a window Windows had not
            # yet handed focus to.
            entry.focus_set()
            dialog.grab_set()
            root.wait_window(dialog)
        finally:
            with contextlib.suppress(Exception):
                dialog.destroy()
        return result["code"]

    return _ui().run(build)


def show_message(title: str, message: str):
    def build(root):
        import tkinter as tk

        dialog = tk.Toplevel(root)
        dialog.title(title)
        dialog.resizable(False, False)

        tk.Label(dialog, text=message, justify="left").pack(padx=20, pady=(16, 8))

        def close(*_):
            dialog.destroy()

        tk.Button(dialog, text="OK", command=close, width=10, default="active").pack(pady=(0, 16))
        dialog.bind("<Return>", close)
        dialog.bind("<Escape>", close)
        dialog.protocol("WM_DELETE_WINDOW", close)

        try:
            _raise_above_everything(dialog)
            dialog.grab_set()
            root.wait_window(dialog)
        finally:
            with contextlib.suppress(Exception):
                dialog.destroy()

    _ui().run(build)


class Tray:
    """Wraps pystray so `main` does not have to know it exists."""

    def __init__(self, service, on_quit):
        self.service = service
        self.on_quit = on_quit
        self._icon = None
        self._stop = threading.Event()

    def _state(self):
        status = self.service.status()
        if not status["registered"]:
            return "unenrolled"
        if status["last_error"]:
            return "error"
        return "running"

    def _refresh(self):
        if self._icon is not None:
            self._icon.icon = _icon_image(COLOURS[self._state()])

    @_guarded
    def _show_status(self, *_):
        show_message("Office Tracker", status_text(self.service.status()))

    @_guarded
    def _enroll(self, *_):
        code = prompt_for_code()
        if not code:
            return
        try:
            self.service.enroll(code)
            show_message("Office Tracker", "This computer is now enrolled.")
        except Exception as exc:
            show_message("Office Tracker", f"Enrolment failed:\n{exc}")
        self._refresh()

    @_guarded
    def _sync_now(self, *_):
        # In its own thread: this does real network I/O, and pystray's win32 backend
        # runs menu callbacks on the same thread as the message loop, so anything
        # blocking here would freeze the tray icon until the request finished. The
        # thread body is guarded too — an unhandled exception there would otherwise
        # just print to the same nowhere-visible stderr as everything else pre-agent.log.
        def worker():
            try:
                result = self.service.sync_now()
            except Exception as exc:
                log.exception("Sync now failed")
                with contextlib.suppress(Exception):
                    show_message("Office Tracker", f"Sync failed:\n{exc}")
                return
            with contextlib.suppress(Exception):
                show_message(
                    "Office Tracker",
                    f"Synced {result['uploaded']} session(s), "
                    f"{result['duplicates']} duplicate(s), {result['rejected']} rejected, "
                    f"{result['pending']} still pending.",
                )
            self._refresh()

        threading.Thread(target=worker, name="tray-sync-now", daemon=True).start()

    @_guarded
    def _quit(self, *_):
        self.on_quit()
        if self._icon is not None:
            self._icon.stop()

    def run(self):
        """Blocking. Runs the tray loop until Quit."""
        import pystray

        menu = pystray.Menu(
            pystray.MenuItem("Status", self._show_status, default=True),
            pystray.MenuItem("Enrol this computer…", self._enroll),
            pystray.MenuItem("Sync now", self._sync_now),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )
        self._icon = pystray.Icon(
            "office-tracker", _icon_image(COLOURS[self._state()]), "Office Tracker", menu
        )

        # Refresh the icon colour periodically so a server outage or a revoked token is
        # visible without opening the menu.
        def poll():
            while not self._stop.wait(15):
                self._refresh()

        threading.Thread(target=poll, name="tray-refresh", daemon=True).start()
        try:
            self._icon.run()
        finally:
            self._stop.set()
