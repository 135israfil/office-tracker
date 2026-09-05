"""SPIKE (throwaway): why does Firefox yield no address bar, and can it be fixed?

Chrome and Edge pass; Firefox returns "no address bar control found". Three candidate
causes, and this script distinguishes them:

  A. Firefox's accessibility engine is dormant, so the UIA tree is essentially empty.
  B. The tree is populated but the address bar carries a different control name.
  C. Firefox exposes IAccessible2/MSAA but not a usable UIA value pattern.

Runs against a throwaway profile on example.com, so the tree it prints is its own.

Run:  .venv/Scripts/python spike_firefox_diagnose.py [--force-a11y]
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time

import psutil
import uiautomation as auto

from run_browser_spike import descendants, kill_tree

FIREFOX = r"C:\Program Files\Mozilla Firefox\firefox.exe"
TEST_URL = "https://example.com/"
MAX_DEPTH = 7
MAX_NODES = 400


def make_profile(force_a11y: bool) -> str:
    profile = tempfile.mkdtemp(prefix="spike-ff-")
    prefs = [
        # The first run of a fresh profile shows an onboarding page that covers the
        # normal chrome. Suppress it so the tree reflects a real browsing window.
        'user_pref("browser.aboutwelcome.enabled", false);',
        'user_pref("browser.startup.homepage_override.mstone", "ignore");',
        'user_pref("datareporting.policy.dataSubmissionPolicyBypassNotification", true);',
        'user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);',
        'user_pref("browser.shell.checkDefaultBrowser", false);',
    ]
    if force_a11y:
        # Firefox keeps its accessibility engine dormant until a client needs it,
        # and its native UIA support sits behind a pref. Ask for both up front.
        prefs += [
            'user_pref("accessibility.force_disabled", 0);',
            'user_pref("widget.uiaenabled", true);',
        ]
    with open(os.path.join(profile, "user.js"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(prefs) + "\n")
    return profile


def walk(control, depth=0, seen=None):
    """Yield (depth, control_type, name, has_value_pattern) breadth-limited."""
    if seen is None:
        seen = [0]
    if depth > MAX_DEPTH or seen[0] >= MAX_NODES:
        return
    try:
        children = control.GetChildren()
    except Exception:  # noqa: BLE001
        return
    for child in children:
        if seen[0] >= MAX_NODES:
            return
        seen[0] += 1
        try:
            name = (child.Name or "")[:58]
            ctype = child.ControlTypeName
            has_value = False
            try:
                pattern = child.GetValuePattern()
                has_value = pattern is not None
            except Exception:  # noqa: BLE001
                has_value = False
            yield depth, ctype, name, has_value
        except Exception:  # noqa: BLE001
            continue
        yield from walk(child, depth + 1, seen)


def main():
    force = "--force-a11y" in sys.argv
    if not os.path.isfile(FIREFOX):
        print("Firefox not found.")
        return

    print(f"Firefox diagnosis (force accessibility prefs: {force})\n")
    profile = make_profile(force)
    proc = None
    try:
        proc = subprocess.Popen([FIREFOX, "-profile", profile, "-no-remote", TEST_URL])
        time.sleep(12)

        pids = descendants(proc.pid)
        for process in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if (process.info["name"] or "").lower() != "firefox.exe":
                    continue
                if profile in " ".join(process.info["cmdline"] or []):
                    pids.add(process.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        auto.SetGlobalSearchTimeout(2.0)
        window = None
        for candidate in auto.GetRootControl().GetChildren():
            if candidate.ClassName == "MozillaWindowClass" and candidate.ProcessId in pids:
                window = candidate
                break

        if window is None:
            print("Could not find a MozillaWindowClass window for the launched PIDs.")
            return

        print(f"Window found: class={window.ClassName!r} name={(window.Name or '')[:50]!r}")
        started = time.perf_counter()
        nodes = list(walk(window))
        elapsed = time.perf_counter() - started
        print(f"Tree walk: {len(nodes)} nodes in {elapsed:.2f}s\n")

        if not nodes:
            print("DIAGNOSIS A: tree is EMPTY - accessibility engine is dormant.")
            return

        edits = [n for n in nodes if n[1] == "EditControl"]
        valued = [n for n in nodes if n[3]]
        # Firefox's URL bar is a combobox wrapping an input, not a plain edit, so the
        # interesting candidates are anything holding a value plus any combo/custom node.
        candidates = [
            n for n in nodes if n[3] or n[1] in {"ComboBoxControl", "CustomControl", "GroupControl"}
        ]

        print(f"Total nodes: {len(nodes)}   EditControls: {len(edits)}   with value: {len(valued)}")
        print("\n--- candidates for the address bar ---")
        print(f"{'depth':>5}  {'control type':<22} {'val':<4} name")
        print("-" * 96)
        for depth, ctype, name, has_value in candidates[:40]:
            marker = "YES" if has_value else "-"
            print(f"{depth:>5}  {ctype:<22} {marker:<4} {name}")

        print("\n--- every control exposing a value pattern (domain redacted) ---")
        for depth, ctype, name, _ in valued:
            print(f"  depth {depth}  {ctype:<20} name={name!r}")

        if valued:
            print("\nDIAGNOSIS B: value-bearing controls exist; the address bar is")
            print("reachable but not as an EditControl. Match on control type + name instead.")
        elif edits:
            print("\nDIAGNOSIS B: edit controls exist under an unmatched name.")
        else:
            print("\nDIAGNOSIS C: tree populated but nothing exposes a usable value.")
    finally:
        if proc is not None:
            kill_tree(proc.pid)
        time.sleep(1.5)
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    main()
