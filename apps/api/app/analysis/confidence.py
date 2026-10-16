from datetime import datetime, timedelta, timezone
from typing import Optional

from .skills import SkillEvidence

MEANINGFUL_LINES = 500
MIN_PROJECTS = 2
MIN_ACTIVE_MONTHS = 3
RECENT_WINDOW = timedelta(days=182)


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def assess(skill: SkillEvidence, now: Optional[datetime] = None) -> tuple[str, list[dict]]:
    """Evidence tier plus the transparent checklist that produced it."""
    now = now or datetime.now(timezone.utc)
    recent = bool(skill.last_active) and now - _parse(skill.last_active) <= RECENT_WINDOW
    projects = len(skill.projects)
    months = len(skill.months)

    factors = [
        {
            "label": "Substantial own code",
            "met": skill.lines >= MEANINGFUL_LINES,
            "detail": f"{skill.lines:,} lines changed by you (needs {MEANINGFUL_LINES:,})",
        },
        {
            "label": "Used across projects",
            "met": projects >= MIN_PROJECTS,
            "detail": f"{projects} project{'s' if projects != 1 else ''}",
        },
        {
            "label": "Accepted by others",
            "met": skill.external_prs >= 1,
            "detail": f"{skill.external_prs} merged PR{'s' if skill.external_prs != 1 else ''} to other people's repos",
        },
        {
            "label": "Sustained over time",
            "met": months >= MIN_ACTIVE_MONTHS,
            "detail": f"active in {months} different month{'s' if months != 1 else ''}",
        },
        {
            "label": "Recent",
            "met": recent,
            "detail": f"last used {skill.last_active[:10]}" if skill.last_active else "no dated activity",
        },
        {
            "label": "Built features",
            "met": skill.feature_contributions >= 1,
            "detail": f"{skill.feature_contributions} feature contribution{'s' if skill.feature_contributions != 1 else ''}",
        },
    ]

    met = sum(f["met"] for f in factors)
    substantial = factors[0]["met"]
    # "Recent" and "Built features" are cheap to meet, so Moderate needs substance or several signals.
    if met >= 4 and substantial:
        tier = "Strong"
    elif met >= 3 or substantial:
        tier = "Moderate"
    else:
        tier = "Limited"
    return tier, factors
