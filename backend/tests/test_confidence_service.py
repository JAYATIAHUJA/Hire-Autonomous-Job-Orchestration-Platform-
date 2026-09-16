from datetime import datetime, timedelta, timezone

from app.services.confidence_service import compute_confidence


def days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def test_strong_needs_volume_breadth_and_recency():
    assert compute_confidence(40, 3, days_ago(10)) == "Strong"


def test_stale_activity_caps_at_moderate():
    assert compute_confidence(40, 3, days_ago(400)) == "Moderate"


def test_multiple_repos_is_moderate():
    assert compute_confidence(4, 2, days_ago(10)) == "Moderate"


def test_low_activity_is_limited():
    assert compute_confidence(2, 1, None) == "Limited"


def test_handles_github_z_suffix():
    recent = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert compute_confidence(31, 3, recent) == "Strong"
