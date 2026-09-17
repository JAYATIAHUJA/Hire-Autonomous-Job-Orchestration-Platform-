"""UTC datetime conversions shared between persistence and serialization.

GitHub hands us ISO-8601 strings; SQLite stores naive datetimes; the API returns
timezone-aware ones. These two helpers are the single place that boundary is crossed.
"""

from datetime import datetime, timezone
from typing import Optional


def to_naive_utc(value: Optional[str]) -> Optional[datetime]:
    """ISO-8601 string (optionally ``Z``-suffixed) -> naive UTC datetime for storage."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)


def to_aware_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Naive UTC datetime from storage -> timezone-aware UTC datetime for the API."""
    return value.replace(tzinfo=timezone.utc) if value else None
