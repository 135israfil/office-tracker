"""SPIKE runner: launch throwaway browser instances and measure domain capture.

Uses an isolated --user-data-dir per browser so the tester's real profile, session and
open tabs are never touched, and restricts the scan to the PIDs it launched so no one
else's browsing is ever read. Everything it starts, it kills.

Run:  .venv/Scripts/python run_browser_spike.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time

import psutil

from spike_browser_domain import scan

TEST_URL = "https://example.com/some/path?with=query#and-fragment"
EXPECTED_DOMAIN = "example.com"

BROWSER_PATHS = {
    "Chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ],
    "Edge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
    "Firefox": [
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
        r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
    ],
}


def find_browser(name):
    for path in BROWSER_PATHS[name]:
        if os.path.isfile(path):
            return path
    return None


def descendants(pid):
    pids = {pid}
    try:
        for child in psutil.Process(pid).children(recursive=True):
            pids.add(child.pid)
    except psutil.NoSuchProcess:
        pass
    return pids


FIREFOX_PREFS = [
    # A brand-new profile opens an onboarding page that covers the normal browser
    # chrome, so a fresh-profile test would fail for a reason no real user hits.
    'user_pref("browser.aboutwelcome.enabled", false);',
    'user_pref("browser.startup.homepage_override.mstone", "ignore");',
    'user_pref("datareporting.policy.dataSubmissionPolicyBypassNotification", true);',
    'user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);',
    'user_pref("browser.shell.checkDefaultBrowser", false);',
]


def launch(name, path, profile_dir, incognito=False):
    if name == "Firefox":
        prefs_path = os.path.join(profile_dir, "user.js")
        with open(prefs_path, "w", encoding="utf-8") as fh:
            for pref in FIREFOX_PREFS:
                fh.write(pref + "\n")
        args = [path, "-profile", profile_dir, "-no-remote"]
        if incognito:
            args.append("-private-window")
        args.append(TEST_URL)
    else:
        args = [
            path,
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--new-window",
        ]
        if incognito:
            args.append("--incognito")
        args.append(TEST_URL)
    return subprocess.Popen(args)


def kill_tree(pid, profile_dir=None, exe_name=None):
    """Kill a launched browser and everything it spawned.

    Killing the process tree from `pid` alone is NOT enough for Firefox: its launcher
    process re-execs and exits, so by the time we look, `pid` is dead and owns no
    children — leaving the real browser and ~90 content processes running, holding file
    locks on the profile we are about to delete. So the profile path is used as the
    authoritative marker, and any orphaned same-exe process left afterwards is swept.
    """
    try:
        process = psutil.Process(pid)
        for child in process.children(recursive=True):
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        process.kill()
    except psutil.NoSuchProcess:
        pass

    if not profile_dir or not exe_name:
        return

    # Anything still running against our throwaway profile is ours to kill.
    roots = []
    for candidate in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if (candidate.info["name"] or "").lower() != exe_name.lower():
                continue
            if profile_dir in " ".join(candidate.info["cmdline"] or []):
                roots.append(psutil.Process(candidate.info["pid"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    victims = []
    for root in roots:
        try:
            victims.extend(root.children(recursive=True))
        except psutil.NoSuchProcess:
            pass
        victims.append(root)

    for victim in victims:
        try:
            victim.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    psutil.wait_procs(victims, timeout=5)


# Firefox is materially slower to reach a UIA-readable state on a cold profile than
# the Chromium pair; 9s proved flaky for it and 20s did not.
SETTLE_SECONDS = {"Chrome": 9, "Edge": 9, "Firefox": 20}


def trial(name, path, incognito, settle_seconds=None):
    settle_seconds = settle_seconds or SETTLE_SECONDS.get(name, 9)
    label = f"{name}{' (private)' if incognito else ''}"
    profile_dir = tempfile.mkdtemp(prefix="spike-profile-")
    proc = None
    try:
        proc = launch(name, path, profile_dir, incognito)
        time.sleep(settle_seconds)

        pids = descendants(proc.pid)
        # Chrome/Edge relaunch through a shim, so also accept same-exe processes
        # that were started after we began and use our throwaway profile.
        exe_name = os.path.basename(path).lower()
        for process in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if (process.info["name"] or "").lower() != exe_name:
                    continue
                cmdline = " ".join(process.info["cmdline"] or [])
                if profile_dir in cmdline:
                    pids.add(process.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Two reads: cold (first ever UIA query) and warm (steady state).
        cold = scan(allowed_pids=pids)
        warm = scan(allowed_pids=pids)

        return {"label": label, "cold": cold, "warm": warm, "windows": len(cold)}
    finally:
        if proc is not None:
            kill_tree(proc.pid, profile_dir=profile_dir, exe_name=os.path.basename(path))
        time.sleep(2.0)
        # Retry: Windows releases file locks slightly after process exit, and a silent
        # ignore_errors here is what left 704MB of profiles behind on the first run.
        for attempt in range(6):
            shutil.rmtree(profile_dir, ignore_errors=(attempt < 5))
            if not os.path.exists(profile_dir):
                break
            time.sleep(1.0)
        else:
            print(f"  WARNING: could not remove {profile_dir}")


def report(result):
    label = result["label"]
    if not result["cold"]:
        print(f"{label:<20} NO WINDOWS FOUND - could not test")
        return

    for phase in ("cold", "warm"):
        for entry in result[phase]:
            domain = entry["domain"]
            verdict = "PASS" if domain == EXPECTED_DOMAIN else "FAIL"
            note = entry["error"] or "OK"
            print(
                f"{label:<20} {phase:<5} {entry['ms']:>6.0f}ms  "
                f"{(domain or '-'):<16} [{verdict}] {note}"
            )


def main():
    print(f"Target URL reduces to: {EXPECTED_DOMAIN}")
    print("Isolated profiles; only launched PIDs are scanned; domains only.\n")
    print(f"{'browser':<20} {'phase':<5} {'time':>8}  {'domain':<16} result")
    print("-" * 82)

    any_tested = False
    for name in ("Chrome", "Edge", "Firefox"):
        path = find_browser(name)
        if path is None:
            print(f"{name:<20} NOT INSTALLED - untested")
            continue
        any_tested = True
        for incognito in (False, True):
            try:
                report(trial(name, path, incognito))
            except Exception as exc:  # noqa: BLE001
                print(f"{name:<20} ERROR {type(exc).__name__}: {str(exc)[:50]}")

    if not any_tested:
        print("\nNo browsers available to test.")


if __name__ == "__main__":
    main()
