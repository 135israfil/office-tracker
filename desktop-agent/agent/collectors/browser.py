"""Website domain detection (§16, §17, §34 Browser Collector).

This is the highest-risk module in the project and the one with the strictest privacy
rule, so both are worth stating before the code:

**The privacy boundary is `extract_domain`.** The address bar's full text exists only as
a local variable inside `_read_domain`. What leaves this module is a bare host or
nothing — never a path, query string, fragment, credential, port or local file path
(§17). The exhaustive case list lives in the tests, not in a comment, because that is
the form that fails the build when someone breaks it.

**Reading is expensive, so it is gated on the window title.** The Phase 1 spike measured
a UI Automation read at 46-259ms against 0.001ms for a window-title read — roughly
42,000× cheaper. Polling the title every two seconds and paying for UIA only when it
changes is the difference between 2.32% of a core and effectively nothing. The title
itself is never stored; it is a change signal and nothing else.

Three findings from that spike are baked into the code below, each of which cost real
debugging time to discover:

1. **Match on control type, not just name.** Chromium exposes the address bar as an
   `EditControl`; Firefox exposes a `ComboBoxControl` and has *zero* EditControls, so a
   name-only or Edit-only matcher finds nothing there at all.
2. **Names are localised**, so matching is substring and case-insensitive, with a
   fall-back to the first control of the expected type.
3. **"Window exists but is not yet readable" is normal.** A browser can take seconds
   after launch before its UIA tree answers. That is a retry, not a gap.
"""

from __future__ import annotations

import logging
import sys
from urllib.parse import urlparse

log = logging.getLogger(__name__)

# §16's initial browser support. Keyed on the executable name the application collector
# already reports, so no second process lookup is needed.
BROWSERS = {
    "chrome.exe": {
        "control_types": ["EditControl"],
        "address_bar_names": ["address and search bar", "address field"],
    },
    "msedge.exe": {
        "control_types": ["EditControl"],
        "address_bar_names": ["address and search bar", "app bar", "address field"],
    },
    "firefox.exe": {
        # ComboBox first: Firefox has no EditControl at all, and trying Edit first there
        # costs a full failed search on every read.
        "control_types": ["ComboBoxControl", "EditControl"],
        "address_bar_names": ["search or enter address", "enter address", "address field"],
    },
}

# macOS's analogue of BROWSERS above, keyed on the bundle-derived executable_name
# application.py's _foreground_app_macos produces ("Google Chrome", not "chrome.exe").
# The values are unused here beyond membership (is_browser) — the actual AX search in
# _find_address_field_macos is a flat toolbar/text-field scan, not a per-browser
# control-type table, because unlike UIA there is no name-localisation problem to work
# around: AXRole is a fixed, non-localised string regardless of system language.
AX_BROWSERS = {"Google Chrome", "Microsoft Edge", "Firefox", "Safari"}

# Schemes that are not web browsing and must never become a website session. `file` is
# on this list for §31 reasons, not tidiness: a local path is file-activity monitoring.
NON_WEB_SCHEMES = {"chrome", "edge", "about", "file", "view-source", "devtools", "data"}

# How many consecutive unreadable samples to ride out before giving up on the domain.
# Five samples is ten seconds — long enough to cover a browser still building its UIA
# tree, short enough that a genuinely closed tab is not credited with minutes it never
# had.
MAX_STALE_READS = 5


def is_browser(executable_name: str | None) -> bool:
    name = executable_name or ""
    # BROWSERS is keyed lowercase with a Windows ".exe" suffix; AX_BROWSERS is keyed
    # exactly as macOS's bundle-derived name comes out, so each is checked in its own
    # native case rather than forcing one casing convention on both platforms.
    return name.lower() in BROWSERS or name in AX_BROWSERS


def extract_domain(raw: str | None) -> str | None:
    """Reduce an address-bar string to a bare domain, or None if it is not a website.

    Everything §17 prohibits is discarded here: paths, query strings, fragments,
    embedded credentials, ports and local file paths. `https://example.com/private/
    account?id=123&token=xxxxx` becomes `example.com`, and a search query becomes
    nothing at all.
    """
    if not raw:
        return None

    candidate = raw.strip()
    if not candidate or " " in candidate:
        # A space means someone typed a search, not an address.
        return None

    scheme, _, remainder = candidate.partition("://")
    if remainder:
        if scheme.lower() in NON_WEB_SCHEMES or scheme.lower() not in {"http", "https"}:
            return None
    elif candidate.split(":")[0].lower() in NON_WEB_SCHEMES:
        # "about:blank" and friends, which carry no "//".
        return None

    if "://" not in candidate:
        candidate = f"https://{candidate}"

    try:
        host = urlparse(candidate).hostname
    except ValueError:
        return None

    if not host or "." not in host:
        # Bare words ("newtab") and single-label intranet hosts are not useful domains.
        return None

    host = host.lower().removeprefix("www.")
    if not all(part and part.replace("-", "").isalnum() for part in host.split(".")):
        return None
    return host


class BrowserCollector:
    """Foreground-tab domain, with title-gated caching.

    `reader` is injected so the whole caching and failure-handling policy is testable
    without a browser: it takes an executable name and returns the address-bar text, or
    None when the window is not readable yet.
    """

    def __init__(self, reader=None):
        self._reader = reader or read_address_bar
        self._signature: str | None = None
        self._domain: str | None = None
        self._stale_reads = 0

    def domain_for(self, app) -> str | None:
        """The domain of the foreground browser tab, or None.

        Only the foreground window is ever consulted, which is what §16 means by "only
        the active browser tab should normally count".
        """
        if not is_browser(app.executable_name):
            self._reset()
            return None

        if app.title_signature and app.title_signature == self._signature:
            # Nothing changed in the window, so nothing changed in the address bar.
            # This branch is the reason the collector is affordable at all.
            return self._domain

        raw = None
        try:
            raw = self._reader(app.executable_name)
        except Exception as exc:
            # Never let a UIA failure take down the sampler; the next tick retries.
            log.debug("Address bar unreadable: %s", type(exc).__name__)

        # `raw` is the only place a full URL exists, and it dies with this frame.
        domain = extract_domain(raw)

        if domain is None and raw is None and self._domain is not None:
            # The window is there but not answering yet. Hold the previous domain
            # briefly rather than recording a gap the user never experienced.
            self._stale_reads += 1
            if self._stale_reads <= MAX_STALE_READS:
                return self._domain
            self._reset()
            return None

        self._signature = app.title_signature
        self._domain = domain
        self._stale_reads = 0
        return domain

    def _reset(self):
        self._signature = None
        self._domain = None
        self._stale_reads = 0


def _find_address_bar(window, names, control_types):  # pragma: no cover - needs a browser
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
            if control.Exists(maxSearchSeconds=0.4, searchIntervalSeconds=0.1):
                return control

    for control_type in control_types:
        factory = getattr(window, control_type, None)
        if factory is None:
            continue
        control = factory(searchDepth=12)
        if control.Exists(maxSearchSeconds=0.3, searchIntervalSeconds=0.1):
            return control
    return None


def _ax_attribute(element, name):  # pragma: no cover - needs a browser
    import ApplicationServices as AX

    err, value = AX.AXUIElementCopyAttributeValue(element, name, None)
    if err != 0:
        return None
    return value


def _find_address_field_macos(window):  # pragma: no cover - needs a browser
    """Depth-limited search for a toolbar text field, the macOS analogue of
    _find_address_bar above. AXRole is a fixed, non-localised string, so — unlike the
    Windows UIA search — there is no name list to try, only a structural search: the
    address field lives in the window's toolbar, with a flat scan of the window's own
    children as a fallback for a browser whose toolbar is laid out unusually.
    """
    children = _ax_attribute(window, "AXChildren") or []
    for child in children:
        if _ax_attribute(child, "AXRole") != "AXToolbar":
            continue
        for grandchild in _ax_attribute(child, "AXChildren") or []:
            if _ax_attribute(grandchild, "AXRole") == "AXTextField":
                return grandchild
    for child in children:
        if _ax_attribute(child, "AXRole") == "AXTextField":
            return child
    return None


def read_address_bar_macos(  # pragma: no cover - needs a browser
    executable_name: str,
) -> str | None:
    """Read the foreground browser window's address bar via the Accessibility API.

    macOS analogue of read_address_bar below: same privacy boundary (tree-reading
    only — see scripts/check_privacy.py, which bans AX's input-synthesis and action
    APIs by name, not by platform), same contract (raw text out, extract_domain
    reduces it, nothing here logs the value). Needs the Accessibility permission
    granted to this app in System Settings; without it this reads nothing and
    returns None, the same honest answer as an unreadable window on Windows.
    """
    if (executable_name or "") not in AX_BROWSERS:
        return None

    try:
        import ApplicationServices as AX
        from AppKit import NSWorkspace
    except ImportError as exc:
        log.error("Browser collector unavailable: %s", exc)
        return None

    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return None

    element = AX.AXUIElementCreateApplication(app.processIdentifier())
    window = _ax_attribute(element, "AXFocusedWindow")
    if window is None:
        return None

    field = _find_address_field_macos(window)
    if field is None:
        return None
    return _ax_attribute(field, "AXValue")


def read_address_bar(executable_name: str) -> str | None:  # pragma: no cover - needs a browser
    """Read the foreground browser window's address bar. Windows only.

    Returns the raw text, which the caller must reduce with `extract_domain` before it
    goes anywhere. Nothing in this function logs the value.
    """
    if sys.platform == "darwin":
        return read_address_bar_macos(executable_name)

    spec = BROWSERS.get((executable_name or "").lower())
    if spec is None:
        return None

    try:
        import uiautomation as auto
    except ImportError as exc:
        log.error("Browser collector unavailable: %s", exc)
        return None

    # Only tree-reading APIs of uiautomation may be used — it is also capable of
    # synthesising input and grabbing bitmaps, which §31 forbids outright. The privacy
    # guard in scripts/check_privacy.py enforces that rather than leaving it to review.
    auto.SetGlobalSearchTimeout(1.0)
    window = auto.GetForegroundControl()
    if window is None:
        return None
    if window.ControlType != auto.ControlType.WindowControl:
        window = window.GetTopLevelControl()
    if window is None:
        return None

    control = _find_address_bar(window, spec["address_bar_names"], spec["control_types"])
    if control is None:
        return None
    return control.GetValuePattern().Value
