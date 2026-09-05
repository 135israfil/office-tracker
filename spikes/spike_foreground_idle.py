"""SPIKE (throwaway): can we reliably read the foreground app and the idle timer?

Phase 1 risk spike per claudedocs/PLAN.md. This is not production code — it exists to
answer a question, and the answers land in claudedocs/SPIKE-REPORT.md.

Questions:
  1. Does GetForegroundWindow -> PID -> psutil give a usable app + exe name?
  2. Does GetLastInputInfo give a usable idle timer, and what are its limits?
  3. What happens on a locked workstation, and over RDP?

Run:  .venv/Scripts/python spike_foreground_idle.py [seconds]
"""

import sys
import time

import psutil
import win32api
import win32con
import win32gui
import win32process


def foreground_app():
    """Return (app_title, process_name, exe_path) for the focused window."""
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        # Happens on the lock screen and during desktop switches.
        return None, None, None

    title = win32gui.GetWindowText(hwnd)
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid)
        name = process.name()
        try:
            exe = process.exe()
        except (psutil.AccessDenied, PermissionError):
            # Elevated processes deny exe() to a non-elevated caller. The name
            # still comes through, which is what §15 actually requires.
            exe = "<access denied>"
        return title, name, exe
    except (psutil.NoSuchProcess, psutil.AccessDenied, Exception) as exc:  # noqa: BLE001
        return title, f"<error: {type(exc).__name__}>", None


def idle_seconds():
    """Seconds since the last keyboard or mouse input, session-wide.

    GetLastInputInfo reports input for the whole session, not per-process, which is
    exactly what §14 wants. Note both values are 32-bit millisecond tick counts that
    wrap every ~49.7 days; the subtraction below is masked to stay correct across
    the wrap instead of returning a huge negative number.
    """
    last_input = win32api.GetLastInputInfo()
    now = win32api.GetTickCount()
    return ((now - last_input) & 0xFFFFFFFF) / 1000.0


def workstation_locked():
    """Best-effort lock detection: no foreground window and no open input desktop."""
    try:
        import win32service

        desktop = win32service.OpenInputDesktop(0, False, win32con.MAXIMUM_ALLOWED)
        if desktop:
            desktop.CloseDesktop()
            return False
        return True
    except Exception:  # noqa: BLE001
        return True


def main():
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    print(f"Sampling foreground app + idle for {duration}s at 2s intervals\n")
    print(f"{'idle_s':>8}  {'locked':>6}  {'process':<22} {'title'}")
    print("-" * 100)

    seen = {}
    samples = 0
    errors = 0

    end = time.time() + duration
    while time.time() < end:
        title, name, _exe = foreground_app()
        idle = idle_seconds()
        locked = workstation_locked()

        if name is None:
            errors += 1
            display_name = "<no foreground window>"
        else:
            display_name = name
            seen[name] = seen.get(name, 0) + 1

        samples += 1
        shown_title = (title or "")[:52]
        print(f"{idle:>8.1f}  {str(locked):>6}  {display_name:<22} {shown_title}")
        time.sleep(2)

    print("\n--- summary ---")
    print(f"samples: {samples}   no-foreground-window: {errors}")
    for name, count in sorted(seen.items(), key=lambda kv: -kv[1]):
        print(f"  {name:<24} {count} samples")


if __name__ == "__main__":
    main()
