"""Rank jobs for one candidate's deck by their saved preferences, and say why.

Simple and explainable on purpose: role words in the title, a preferred city (or
remote), and seniority that fits the experience band. Each match adds a reason the
card can show ("Matches Backend engineer", "In Bengaluru", "Fits 1–3 years").
"""

import re
from typing import Any, Optional

from .ats_registry import is_india_location

# Words in a role that say nothing about which role it is.
_GENERIC = {"engineer", "engineering", "developer", "software", "sde", "swe", "role", "job", "jobs", "and", "the"}

# Experience band -> the seniority labels (from ingestion) that fit it.
_FITS = {
    "0-1": {"Internship", "Entry-Level (0-2 yrs)"},
    "1-3": {"Entry-Level (0-2 yrs)", "Mid-Level (2-5 yrs)"},
    "3-5": {"Mid-Level (2-5 yrs)"},
    "5-8": {"Mid-Level (2-5 yrs)", "Senior (5+ yrs)"},
    "8-12": {"Senior (5+ yrs)"},
    "12+": {"Senior (5+ yrs)"},
}
_BAND_WORDS = {"0-1": "interns and freshers", "1-3": "1–3 years", "3-5": "3–5 years", "5-8": "5–8 years",
               "8-12": "8–12 years", "12+": "12+ years"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9+#.]+", text.lower()) if len(w) > 1}


# Role (4) + place (2) + level (1): the most a job can score.
MAX_POINTS = 7


def percent(points: int) -> int:
    """The score as a 0-100 match, for the card."""
    return max(0, min(100, round(points / MAX_POINTS * 100)))


def score(
    job: Any, prefs: Optional[dict[str, Any]], *, breaker_text: Optional[str] = None
) -> tuple[int, list[str]]:
    """(score, reasons) for a Job row. Higher is a better fit; 0 means no signal.

    ``breaker_text`` overrides the text deal-breakers are matched against (title
    plus description by default), so bulk ranking can pass cheap columns instead
    of loading every job's 20 KB description.
    """
    if not prefs:
        return 0, []
    points, reasons = 0, []
    title = _words(job.title or "")

    for role in prefs.get("roles") or []:
        words = _words(role)
        specific = words - _GENERIC
        if (specific and specific <= title) or (not specific and words and words <= title):
            points += 4
            reasons.append(f"Matches {role}")
            break
        if specific & title:
            points += 2
            reasons.append(f"Close to {role}")
            break

    location = (job.location or "").lower()
    cities = [c for c in (prefs.get("locations") or []) if c.strip()]
    city = next((c for c in cities if c.lower().split(",")[0].strip() in location), None)
    remote = job.is_remote or "remote" in location
    if city:
        points += 2
        reasons.append(f"In {city.split(',')[0].strip()}")
    elif prefs.get("remote_ok") and remote:
        in_india = is_india_location(location)
        points += 2 if in_india else 1  # a remote role run from India beats one run from abroad
        reasons.append("Remote, India" if in_india else "Remote")
    elif cities:
        points -= 1  # elsewhere: still shown, but after the ones in their cities

    band = prefs.get("experience_band")
    level = job.experience_level or ""
    if band in _FITS:
        if level in _FITS[band]:
            points += 1
            reasons.append(f"Fits {_BAND_WORDS[band]}")
        elif band in ("0-1", "1-3") and level == "Senior (5+ yrs)":
            points -= 4  # a staff role is noise for a fresher

    breakers = [b.lower() for b in prefs.get("deal_breakers") or [] if b.strip()]
    text = breaker_text if breaker_text is not None else f"{job.title} {job.raw_description or ''}"
    if any(b in text.lower() for b in breakers if len(b) > 3):
        points -= 5
    return points, reasons
