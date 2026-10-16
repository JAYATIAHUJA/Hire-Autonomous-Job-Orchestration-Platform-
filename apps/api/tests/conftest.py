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
    # Tests run on the demo jobs and never read real employer boards.
    monkeypatch.setattr(settings, "demo_jobs_enabled", True)
    monkeypatch.setattr(settings, "ats_registry_path", "/nonexistent/registry.json")
    monkeypatch.setattr(settings, "ats_boards_per_round", 0)
    monkeypatch.setattr(settings, "consent_signing_secret", TEST_SIGNING_SECRET)


def pytest_configure(config):
    config.addinivalue_line("markers", "enforce_consent: keep the DPDP consent gates on for this test")


@pytest.fixture(autouse=True)
def _consent_gates_open(request):
    """Feature tests predate the DPDP consent gates and are not about them, so the gates
    pass any logged-in account. Tests marked ``enforce_consent`` (test_me_*.py) keep them."""
    from fastapi import Depends

    from app.auth.consents import require_github_consent, require_resume_consent
    from app.auth.deps import get_current_user
    from app.main import app

    if request.node.get_closest_marker("enforce_consent"):
        yield
        return

    def logged_in(account=Depends(get_current_user)):
        return account

    gates = (require_github_consent, require_resume_consent)
    for gate in gates:
        app.dependency_overrides[gate] = logged_in
    yield
    for gate in gates:
        app.dependency_overrides.pop(gate, None)
