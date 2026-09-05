"""Unit tests for the privacy boundary (README.txt §17).

Synthetic inputs only — no real browsing data. These assertions are the ones that must
survive into the production collector in Phase 6, so they are written as if they were
already production tests.

Run:  .venv/Scripts/python test_extract_domain.py
"""

from spike_browser_domain import extract_domain

CASES = [
    # (address bar text, expected domain, why it matters)
    ("github.com", "github.com", "Chrome hides the scheme for a plain host"),
    ("https://github.com", "github.com", "explicit scheme"),
    ("www.google.com", "google.com", "www. is stripped so it groups with google.com"),
    ("https://www.google.com/", "google.com", "trailing slash"),
    (
        "https://example.com/private/account?id=123&token=secret",
        "example.com",
        "§17: path, query and token must be discarded",
    ),
    (
        "https://mail.google.com/mail/u/0/#inbox",
        "mail.google.com",
        "§17: fragment discarded, subdomain kept",
    ),
    (
        "https://user:password@example.com/x",
        "example.com",
        "§17: embedded credentials must never survive",
    ),
    ("https://example.com:8443/app", "example.com", "port discarded"),
    ("HTTPS://EXAMPLE.COM/Path", "example.com", "host lowercased for grouping"),
    ("stackoverflow.com/questions/1234", "stackoverflow.com", "host-only, no scheme"),
    # Things that must NOT become website sessions
    ("how to center a div", None, "a search query, not a URL"),
    ("chrome://settings/privacy", None, "browser internal page"),
    ("edge://downloads", None, "browser internal page"),
    ("about:blank", None, "browser internal page"),
    ("file:///C:/Users/me/tax-return.pdf", None, "§31: local file paths are off limits"),
    ("view-source:https://example.com", None, "not normal browsing"),
    ("data:text/html,<h1>hi</h1>", None, "inline data URL"),
    ("", None, "empty address bar"),
    (None, None, "no address bar value"),
    ("   ", None, "whitespace only"),
    ("newtab", None, "bare word, not a domain"),
    ("localhost", None, "single-label host is not a useful domain"),
]


def main():
    failures = []
    for raw, expected, reason in CASES:
        actual = extract_domain(raw)
        status = "ok  " if actual == expected else "FAIL"
        if actual != expected:
            failures.append((raw, expected, actual, reason))
        shown = "<None>" if raw is None else (raw if len(raw) <= 46 else raw[:43] + "...")
        print(f"[{status}] {shown:<48} -> {str(actual):<20} ({reason})")

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S):")
        for raw, expected, actual, reason in failures:
            print(f"  {raw!r}: expected {expected!r}, got {actual!r}  ({reason})")
        raise SystemExit(1)

    print(f"All {len(CASES)} cases passed.")
    print("No full URL, path, query, credential or local file path survives extraction.")


if __name__ == "__main__":
    main()
