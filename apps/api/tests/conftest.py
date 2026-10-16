"""Shared test setup: hermetic and with a real-length signing secret.

Tests never reach the network (B10). Live feeds are off, so the deck is built from
the fixtures in ``app/jobs/ingestion/feeds.py`` and results don't change from day to day.
"""

import pytest

from app.config import settings

TEST_SIGNING_SECRET = "test-only-consent-secret-0123456789abcdef"


@pytest.fixture(autouse=True)
def _hermetic_settings(monkeypatch):
    monkeypatch.setattr(settings, "live_feeds_enabled", False)
    monkeypatch.setattr(settings, "consent_signing_secret", TEST_SIGNING_SECRET)
