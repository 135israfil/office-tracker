"""SPIKE (throwaway): how expensive is address-bar reading, and can we avoid most of it?

The Phase 1 measurement put a UIA address-bar read at ~55ms. On the planned 2s poll that
is ~2.75% of a core burned continuously while a browser is focused — more than an agent
that is supposed to be invisible should cost.

Hypothesis: the window title changes on every navigation and every tab switch, and
reading it via GetWindowText is orders of magnitude cheaper than a UIA tree walk. If so
the collector can poll the title and only fall back to UIA when the title changes,
turning a continuous cost into a per-navigation one.

Run:  .venv/Scripts/python spike_read_cost.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time

import psutil
import uiautomation as auto
import win32gui

from run_browser_spike import descendants, kill_tree
from spike_browser_domain import BROWSERS, read_domain

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]
TEST_URL = "https://example.com/"
SAMPLES = 40


def find_chrome():
    for path in CHROME_PATHS:
        if os.path.isfile(path):
            return path
    return None


def time_calls(fn, samples):
    """Return (median_ms, max_ms) over `samples` calls."""
    timings = []
    for _ in range(samples):
        start = time.perf_counter()
        fn()
        timings.append((time.perf_counter() - start) * 1000)
    timings.sort()
    return timings[len(timings) // 2], timings[-1]


def main():
    chrome = find_chrome()
    if chrome is None:
        print("Chrome not installed - cannot run.")
        return

    profile = tempfile.mkdtemp(prefix="spike-cost-")
    proc = None
    try:
        proc = subprocess.Popen(
            [
                chrome,
                f"--user-data-dir={profile}",
                "--no-first-run",
                "--no-default-browser-check",
                "--new-window",
                TEST_URL,
            ]
        )
        time.sleep(9)

        pids = descendants(proc.pid)
        for process in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if (process.info["name"] or "").lower() != "chrome.exe":
                    continue
                if profile in " ".join(process.info["cmdline"] or []):
                    pids.add(process.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        auto.SetGlobalSearchTimeout(1.0)
        target = None
        for window in auto.GetRootControl().GetChildren():
            if window.ClassName == "Chrome_WidgetWin_1" and window.ProcessId in pids:
                if window.BoundingRectangle and window.BoundingRectangle.width() > 0:
                    target = window
                    break

        if target is None:
            print("Could not locate the launched Chrome window.")
            return

        hwnd = target.NativeWindowHandle
        names = BROWSERS["chrome.exe"]["address_bar_names"]

        title_median, title_max = time_calls(lambda: win32gui.GetWindowText(hwnd), SAMPLES)
        uia_median, uia_max = time_calls(lambda: read_domain(target, names), SAMPLES)

        print(f"Samples per method: {SAMPLES}\n")
        print(f"{'method':<34} {'median':>10} {'max':>10}")
        print("-" * 58)
        print(f"{'GetWindowText (title only)':<34} {title_median:>9.3f}ms {title_max:>9.3f}ms")
        print(f"{'UIA address bar read':<34} {uia_median:>9.1f}ms {uia_max:>9.1f}ms")

        ratio = uia_median / title_median if title_median else float("inf")
        print(f"\nUIA read is ~{ratio:,.0f}x more expensive than a title read.")

        poll = 2.0
        always = (uia_median / 1000) / poll * 100
        cheap = (title_median / 1000) / poll * 100
        print(f"\nContinuous cost on a {poll:.0f}s poll while a browser is focused:")
        print(f"  UIA every tick:        {always:.2f}% of one core")
        print(f"  Title every tick:      {cheap:.4f}% of one core")
        print(f"  -> title-gated polling removes ~{always - cheap:.2f} points of steady load,")
        print("     paying the UIA cost only when the title changes (navigation/tab switch).")

        print("\nTitle sample (truncated, spike only):", win32gui.GetWindowText(hwnd)[:40])
    finally:
        if proc is not None:
            kill_tree(proc.pid)
        time.sleep(1.5)
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    main()
