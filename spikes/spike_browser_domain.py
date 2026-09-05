"""SPIKE (throwaway): can we read the active tab's DOMAIN from Chrome/Edge/Firefox?

Phase 1 risk spike per claudedocs/PLAN.md — the single highest-risk item in the project.
Findings land in claudedocs/SPIKE-REPORT.md.

Questions:
  1. Can UI Automation read the address bar of each browser?
  2. Does it work on background windows, or only the foreground one?
  3. How slow is it? (It runs on a 2s poll in production.)
  4. Does it survive incognito/private windows?

PRIVACY: this script never prints or returns a full URL. `extract_domain` reduces the
address bar to a bare host inside the function and the caller only ever sees that, which
is the same discipline README.txt §17 demands of the real collector. That rule applies
to spike code too — this runs against a real person's browser.

Run:  .venv/Scripts/python spike_browser_domain.py
"""

from __future__ import annotations

import time
from urllib.parse import urlparse

import uiautomation as auto

# Address-bar control names AND control types differ per browser. Chromium exposes an
# EditControl; Firefox exposes a ComboBoxControl wrapping its input (verified against
# Firefox 154 - searching for an EditControl there finds nothing at all). Matching is
# substring + case-insensitive because the strings are localised and change by version.
BROWSERS = {
    "chrome.exe": {
        "label": "Chrome",
        "window_class": "Chrome_WidgetWin_1",
        "control_types": ["EditControl"],
        "address_bar_names": ["address and search bar", "address field"],
    },
    "msedge.exe": {
        "label": "Edge",
        "window_class": "Chrome_WidgetWin_1",
        "control_types": ["EditControl"],
        "address_bar_names": ["address and search bar", "app bar", "address field"],
    },
    "firefox.exe": {
        "label": "Firefox",
        "window_class": "MozillaWindowClass",
        "control_types": ["ComboBoxControl", "EditControl"],
        "address_bar_names": ["search or enter address", "enter address", "address field"],
    },
}

# Schemes that are not web browsing and must never become a "website" session.
NON_WEB_SCHEMES = {"chrome", "edge", "about", "file", "view-source", "devtools", "data"}


def extract_domain(raw: str | None) -> str | None:
    """Reduce an address-bar string to a bare domain, or None if it is not a website.

    This is the privacy boundary. The full string exists only as a local here; only the
    host escapes. Paths, query strings, fragments, credentials and ports are dropped.
    """
    if not raw:
        return None

    candidate = raw.strip()
    if not candidate or " " in candidate:
        # Spaces mean a search query, not a URL.
        return None

    scheme, _, remainder = candidate.partition("://")
    if remainder:
        if scheme.lower() in NON_WEB_SCHEMES:
            return None
        if scheme.lower() not in {"http", "https"}:
            return None
    elif candidate.split(":")[0].lower() in NON_WEB_SCHEMES:
        # e.g. "about:blank" with no "//"
        return None

    if "://" not in candidate:
        candidate = f"https://{candidate}"

    try:
        host = urlparse(candidate).hostname
    except ValueError:
        return None

    if not host or "." not in host:
        # Bare words ("newtab") and intranet single-label hosts are not useful domains.
        return None

    host = host.lower().removeprefix("www.")
    if not all(part and part.replace("-", "").isalnum() for part in host.split(".")):
        return None
    return host


def find_address_bar(window, names, control_types=("EditControl",)):
    """Depth-limited search for the address bar control.

    Tries each (control type, name) pair, then falls back to the first control of the
    expected type. The fallback matters because the names are localised: on a
    non-English Windows the name match fails but the structure is unchanged.
    """
    for control_type in control_types:
        factory = getattr(window, control_type, None)
        if factory is None:
            continue
        for name in names:
            control = factory(
                searchDepth=12,
                Compare=lambda c, _d, target=name: target in (c.Name or "").lower(),
            )
            if control.Exists(maxSearchSeconds=0.6, searchIntervalSeconds=0.1):
                return control

    for control_type in control_types:
        factory = getattr(window, control_type, None)
        if factory is None:
            continue
        control = factory(searchDepth=12)
        if control.Exists(maxSearchSeconds=0.4, searchIntervalSeconds=0.1):
            return control
    return None


def read_domain(window, names, control_types=("EditControl",)):
    control = find_address_bar(window, names, control_types)
    if control is None:
        return None, "no address bar control found"
    try:
        value = control.GetValuePattern().Value
    except Exception as exc:  # noqa: BLE001
        return None, f"value pattern failed: {type(exc).__name__}"
    domain = extract_domain(value)
    if domain is None:
        return None, "address bar held no web domain (search, blank or internal page)"
    return domain, None


def scan(allowed_pids=None):
    """Scan browser windows for domains.

    allowed_pids restricts the scan to specific processes. The spike runner uses it to
    look only at the throwaway browser instances it launched, so a real person's open
    tabs are never read or printed while testing.
    """
    auto.SetGlobalSearchTimeout(1.0)
    results = []
    root = auto.GetRootControl()

    for window in root.GetChildren():
        try:
            class_name = window.ClassName or ""
            process_name = None
            for exe, spec in BROWSERS.items():
                if class_name == spec["window_class"]:
                    process_name = exe
                    break
            if process_name is None:
                continue
            if allowed_pids is not None and window.ProcessId not in allowed_pids:
                continue
            if not window.BoundingRectangle or window.BoundingRectangle.width() == 0:
                continue

            spec = BROWSERS[process_name]
            started = time.perf_counter()
            domain, error = read_domain(
                window, spec["address_bar_names"], spec["control_types"]
            )
            elapsed_ms = (time.perf_counter() - started) * 1000

            results.append(
                {
                    "browser": spec["label"],
                    "domain": domain,
                    "error": error,
                    "ms": elapsed_ms,
                }
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                {"browser": class_name, "domain": None, "error": str(exc)[:60], "ms": 0.0}
            )
    return results


def main():
    print("Scanning browser windows (domains only - never full URLs)\n")
    results = scan()

    if not results:
        print("No browser windows found.")
        return

    print(f"{'browser':<10} {'ms':>7}  {'domain':<28} note")
    print("-" * 88)
    for r in results:
        print(
            f"{r['browser']:<10} {r['ms']:>7.0f}  "
            f"{(r['domain'] or '-'):<28} {r['error'] or 'OK'}"
        )

    ok = sum(1 for r in results if r["domain"])
    print(f"\n{ok}/{len(results)} browser windows yielded a domain")


if __name__ == "__main__":
    main()
