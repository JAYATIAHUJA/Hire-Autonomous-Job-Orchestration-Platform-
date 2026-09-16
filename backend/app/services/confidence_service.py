from datetime import datetime, timedelta, timezone
from typing import Optional

RECENT_WINDOW = timedelta(days=182)


def compute_confidence(commit_count: int, repo_count: int, last_active: Optional[str]) -> str:
    recent = False
    if last_active:
        last_dt = datetime.fromisoformat(last_active.replace("Z", "+00:00"))
        recent = datetime.now(timezone.utc) - last_dt <= RECENT_WINDOW

    if commit_count > 30 and repo_count > 2 and recent:
        return "Strong"
    if commit_count >= 10 or repo_count >= 2:
        return "Moderate"
    return "Limited"
