"""Phase 6: website domain capture (§16, §17).

The first class here is the privacy boundary, written as a table because that is what it
is: a list of things that must never survive into stored data. It carries forward the
Phase 1 spike's cases unchanged — they were written as if they were already production
tests, and now they are.

The rest covers the two properties that make the collector affordable and honest: it
reads only when the window title changed, and it consults only the foreground window.
"""

from __future__ import annotations

import datetime as dt

import pytest

from agent.collectors.application import EMPTY, ForegroundApp
from agent.collectors.browser import (
    MAX_STALE_READS,
    BrowserCollector,
    extract_domain,
    is_browser,
)
from agent.sessions import (
    TYPE_APPLICATION,
    TYPE_WEBSITE,
    Sample,
    SessionBuilder,
)

START = dt.datetime(2026, 8, 19, 9, 0, tzinfo=dt.UTC)

CHROME = ForegroundApp(
    application_name="Google Chrome", executable_name="chrome.exe", title_signature="t1"
)
CHROME_NEW_TAB = ForegroundApp(
    application_name="Google Chrome", executable_name="chrome.exe", title_signature="t2"
)
FIREFOX = ForegroundApp(
    application_name="Firefox", executable_name="firefox.exe", title_signature="f1"
)
VSCODE = ForegroundApp(
    application_name="Visual Studio Code", executable_name="Code.exe", title_signature="v1"
)


def at(seconds):
    return START + dt.timedelta(seconds=seconds)


# --- The privacy boundary ---------------------------------------------------


class TestExtractDomain:
    @pytest.mark.parametrize(
        ("raw", "expected", "why"),
        [
            ("github.com", "github.com", "Chrome hides the scheme for a plain host"),
            ("https://github.com", "github.com", "explicit scheme"),
            ("www.google.com", "google.com", "www. stripped so it groups with google.com"),
            ("https://www.google.com/", "google.com", "trailing slash"),
            ("stackoverflow.com/questions/1234", "stackoverflow.com", "host-only, no scheme"),
            ("HTTPS://EXAMPLE.COM/Path", "example.com", "host lowercased for grouping"),
            ("https://mail.google.com/mail/u/0/#inbox", "mail.google.com", "subdomain kept"),
        ],
    )
    def test_websites_reduce_to_a_bare_host(self, raw, expected, why):
        assert extract_domain(raw) == expected, why

    @pytest.mark.parametrize(
        ("raw", "expected", "why"),
        [
            (
                "https://example.com/private/account?id=123&token=secret",
                "example.com",
                "§17: path, query and token discarded",
            ),
            (
                "https://user:password@example.com/x",
                "example.com",
                "§17: embedded credentials must never survive",
            ),
            ("https://example.com:8443/app", "example.com", "port discarded"),
            ("https://example.com/#/settings/api-key", "example.com", "fragment discarded"),
        ],
    )
    def test_everything_after_the_host_is_discarded(self, raw, expected, why):
        assert extract_domain(raw) == expected, why

    @pytest.mark.parametrize(
        ("raw", "why"),
        [
            ("how to center a div", "a search query, not a URL"),
            ("chrome://settings/privacy", "browser internal page"),
            ("edge://downloads", "browser internal page"),
            ("about:blank", "browser internal page"),
            ("file:///C:/Users/me/tax-return.pdf", "§31: local file paths are off limits"),
            ("view-source:https://example.com", "not normal browsing"),
            ("data:text/html,<h1>hi</h1>", "inline data URL"),
            ("", "empty address bar"),
            (None, "no address bar value"),
            ("   ", "whitespace only"),
            ("newtab", "bare word, not a domain"),
            ("localhost", "single-label host is not a useful domain"),
        ],
    )
    def test_things_that_are_not_websites_yield_nothing(self, raw, why):
        assert extract_domain(raw) is None, why

    def test_no_url_punctuation_can_ever_survive(self):
        """A blanket assertion, so a future 'small' change cannot leak a path."""
        urls = [
            "https://example.com/private/account?id=1&token=abc#frag",
            "http://user:pw@intranet.example.com:8080/hr/salaries.xlsx",
            "https://mail.google.com/mail/u/0/#inbox/FMfcgz",
        ]
        for url in urls:
            domain = extract_domain(url)
            assert domain is not None
            assert not any(marker in domain for marker in "/?#@:")
            # And nothing recognisable from the sensitive part of the URL.
            for secret in ("token", "salaries", "FMfcgz", "abc", "hr"):
                assert secret not in domain


class TestBrowserDetection:
    def test_the_three_supported_browsers_are_recognised(self):
        assert is_browser("chrome.exe")
        assert is_browser("msedge.exe")
        assert is_browser("FIREFOX.EXE")

    def test_everything_else_is_not(self):
        assert not is_browser("Code.exe")
        assert not is_browser("")
        assert not is_browser(None)


# --- The collector ----------------------------------------------------------


class RecordingReader:
    """Stands in for the UI Automation read, counting how often it happens."""

    def __init__(self, values=None):
        self.calls = 0
        self.values = list(values or [])
        self.default = "https://github.com/anthropics/claude-code"

    def __call__(self, executable_name):
        self.calls += 1
        if self.values:
            value = self.values.pop(0)
            if isinstance(value, Exception):
                raise value
            return value
        return self.default


class TestBrowserCollector:
    def test_a_browser_window_yields_a_domain(self):
        collector = BrowserCollector(reader=RecordingReader())
        assert collector.domain_for(CHROME) == "github.com"

    def test_a_non_browser_is_never_read(self):
        reader = RecordingReader()
        collector = BrowserCollector(reader=reader)

        assert collector.domain_for(VSCODE) is None
        assert collector.domain_for(EMPTY) is None
        # Not merely "returns None": the expensive call must not happen at all.
        assert reader.calls == 0

    def test_an_unchanged_window_title_is_not_re_read(self):
        """Title gating is what makes this collector affordable.

        The Phase 1 spike measured a UIA read at 46-259ms against 0.001ms for a title
        read. Re-reading on every 2s tick would cost ~2.3% of a core; this makes it
        effectively free.
        """
        reader = RecordingReader()
        collector = BrowserCollector(reader=reader)

        for _ in range(30):  # a minute of sampling on one page
            assert collector.domain_for(CHROME) == "github.com"

        assert reader.calls == 1

    def test_a_changed_title_triggers_a_fresh_read(self):
        reader = RecordingReader(values=["https://github.com", "https://stackoverflow.com/q/1"])
        collector = BrowserCollector(reader=reader)

        assert collector.domain_for(CHROME) == "github.com"
        assert collector.domain_for(CHROME_NEW_TAB) == "stackoverflow.com"
        assert reader.calls == 2

    def test_switching_away_from_the_browser_clears_the_cache(self):
        reader = RecordingReader()
        collector = BrowserCollector(reader=reader)

        collector.domain_for(CHROME)
        assert collector.domain_for(VSCODE) is None
        # Returning to a window with the same title must re-read rather than trust a
        # cache from before the user was somewhere else entirely.
        collector.domain_for(CHROME)
        assert reader.calls == 2

    def test_an_unreadable_window_holds_the_last_domain_briefly(self):
        """ "Window exists but is not yet readable" is normal, per the spike.

        A browser can take seconds after launch before its UIA tree answers. Recording a
        gap there would mean the user's actual browsing shows up as nothing.
        """
        reader = RecordingReader(values=["https://github.com"] + [None] * 10)
        collector = BrowserCollector(reader=reader)

        assert collector.domain_for(CHROME) == "github.com"
        for _ in range(MAX_STALE_READS):
            assert collector.domain_for(CHROME_NEW_TAB) == "github.com"

        # But not forever: a genuinely closed tab must not be credited with minutes it
        # never had.
        assert collector.domain_for(CHROME_NEW_TAB) is None

    def test_a_failing_read_never_escapes(self):
        reader = RecordingReader(values=[RuntimeError("COM is having a day")])
        collector = BrowserCollector(reader=reader)
        # The sampler must survive whatever UI Automation does.
        assert collector.domain_for(CHROME) is None

    def test_a_search_query_produces_no_website_session(self):
        reader = RecordingReader(values=["how to center a div"])
        collector = BrowserCollector(reader=reader)
        assert collector.domain_for(CHROME) is None

    def test_the_collector_never_returns_a_url(self):
        reader = RecordingReader(
            values=["https://intranet.example.com:8443/hr/salaries.xlsx?token=abc"]
        )
        collector = BrowserCollector(reader=reader)

        domain = collector.domain_for(FIREFOX)
        assert domain == "intranet.example.com"
        assert "salaries" not in domain
        assert "token" not in domain


# --- The website track ------------------------------------------------------


def browse(builder, start_seconds, end_seconds, domain, *, step=2, app=CHROME, state="ONLINE"):
    closed = []
    moment = start_seconds
    while moment <= end_seconds:
        closed.append(
            builder.observe(Sample(at=at(moment), state=state, app=app, website_domain=domain))
        )
        moment += step
    return [session for group in closed for session in group]


class TestWebsiteTrack:
    def test_a_domain_change_closes_the_website_session(self):
        builder = SessionBuilder()
        assert browse(builder, 0, 120, "github.com") == []

        closed = builder.observe(
            Sample(at=at(122), state="ONLINE", app=CHROME_NEW_TAB, website_domain="google.com")
        )

        assert len(closed) == 1
        assert closed[0]["activity_type"] == TYPE_WEBSITE
        assert closed[0]["website_domain"] == "github.com"
        assert closed[0]["duration_seconds"] == 122

    def test_website_and_application_sessions_run_in_parallel(self):
        builder = SessionBuilder()
        browse(builder, 0, 60, "github.com")

        # §18: nothing sums across types. "Chrome for an hour" and "github.com for
        # twenty minutes" are both true at once.
        assert set(builder.open_tracks) == {"state", "application", "website"}

    def test_leaving_the_browser_closes_the_website_but_not_the_state(self):
        builder = SessionBuilder()
        browse(builder, 0, 60, "github.com")

        closed = builder.observe(Sample(at=at(62), state="ONLINE", app=VSCODE, website_domain=""))

        types = {session["activity_type"] for session in closed}
        assert types == {TYPE_WEBSITE, TYPE_APPLICATION}
        assert builder.open_tracks["state"] == "ACTIVE"

    def test_going_idle_closes_the_website_session(self):
        builder = SessionBuilder()
        browse(builder, 0, 60, "github.com")

        closed = builder.observe(
            Sample(at=at(62), state="IDLE", app=CHROME, website_domain="github.com")
        )

        # A tab left open while someone is at lunch is not twenty minutes of reading it.
        assert TYPE_WEBSITE in {session["activity_type"] for session in closed}
        assert "website" not in builder.open_tracks

    def test_a_long_read_is_split_at_the_cap(self):
        builder = SessionBuilder(max_session_seconds=60)
        closed = browse(builder, 0, 60, "github.com")

        website = [s for s in closed if s["activity_type"] == TYPE_WEBSITE]
        assert len(website) == 1
        assert website[0]["duration_seconds"] == 60
        assert builder.open_tracks["website"] == TYPE_WEBSITE

    def test_website_sessions_carry_no_application_fields(self):
        builder = SessionBuilder()
        browse(builder, 0, 60, "github.com")
        closed = builder.observe(
            Sample(at=at(62), state="ONLINE", app=CHROME_NEW_TAB, website_domain="google.com")
        )

        session = closed[0]
        assert session["website_domain"] == "github.com"
        assert session["application_name"] == ""
        assert session["executable_name"] == ""
