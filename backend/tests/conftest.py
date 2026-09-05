"""Shared pytest configuration."""

import pytest


@pytest.fixture(autouse=True)
def fast_password_hashing(settings):
    """Use a cheap hasher in tests.

    PBKDF2 is deliberately slow, which is correct in production and pointless in a test
    suite that creates hundreds of users. This cut the Phase 2 suite from ~85s to a few
    seconds. Production hashing is untouched — `settings` here is pytest-django's
    per-test override.
    """
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture(autouse=True)
def isolate_throttles():
    """Reset rate-limit counters between tests.

    DRF keeps throttle history in the default cache, which is process-wide and therefore
    shared by every test in a run. Without this, the thirtieth agent registration in the
    whole suite starts failing with a 429 — a failure with nothing to do with the test
    that trips it. Throttling itself stays enabled, so the tests that assert on it
    still work.
    """
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()
