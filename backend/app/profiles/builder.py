"""Assemble a ``User`` ORM graph from analysis output.

Pure, in-memory construction — no database session, no I/O. Given the dict that
``fetch_service`` produces, this returns a detached ``User`` with its projects,
contributions and skills populated; persisting it is the repository's job.
"""

import json
from typing import Any

from .. import models
from ..analysis.confidence import assess
from ..analysis.contribution import Contribution
from ..analysis.highlights import top_contributions
from ..analysis.skills import SkillEvidence, infer_skills
from ..services.metrics_service import timeline, work_mix
from ..time_utils import to_naive_utc

_HIGHLIGHTS_PER_SKILL = 3


def build_profile(username: str, data: dict[str, Any]) -> models.User:
    """Build the full ``User`` graph (projects + contributions + skills) for one analysis run."""
    contributions: list[Contribution] = data["contributions"]

    user = models.User(
        username=username,
        analysis_mode=data["analysis_mode"],
        timeline_json=json.dumps(timeline(data["activity_dates"])),
        work_mix_json=json.dumps(work_mix(contributions)),
    )
    user.projects = [_project_row(p) for p in data["projects"]]

    # One ORM row per contribution, keyed by object identity so skills can point
    # their highlights at the very same rows (the many-to-many is by reference).
    rows = {id(c): _contribution_row(c) for c in contributions}
    user.contributions = list(rows.values())
    user.skills = [_skill_row(evidence, rows) for evidence in infer_skills(contributions).values()]
    return user


def _project_row(project: dict[str, Any]) -> models.Project:
    scalar_fields = {k: v for k, v in project.items() if k not in {"first_contribution", "last_contribution"}}
    return models.Project(
        **scalar_fields,
        first_contribution=to_naive_utc(project["first_contribution"]),
        last_contribution=to_naive_utc(project["last_contribution"]),
    )


def _contribution_row(c: Contribution) -> models.Contribution:
    return models.Contribution(
        kind=c.kind,
        repo_full_name=c.repo,
        url=c.url,
        title=c.title,
        type=c.type,
        date=to_naive_utc(c.date),
        meaningful_additions=c.meaningful_additions,
        meaningful_deletions=c.meaningful_deletions,
        files_touched=c.files_touched,
        is_external=c.external,
        is_bulk=c.bulk,
        weight=c.weight,
        languages_json=json.dumps([lang for lang, _ in c.language_lines.most_common()]),
    )


def _skill_row(evidence: SkillEvidence, rows: dict[int, models.Contribution]) -> models.Skill:
    tier, factors = assess(evidence)
    return models.Skill(
        name=evidence.name,
        confidence_tier=tier,
        weight=round(evidence.weight, 3),
        lines=evidence.lines,
        project_count=len(evidence.projects),
        contribution_count=len(evidence.contributions),
        external_pr_count=evidence.external_prs,
        active_months=len(evidence.months),
        first_active=to_naive_utc(evidence.first_active),
        last_active=to_naive_utc(evidence.last_active),
        factors_json=json.dumps(factors),
        detected_via_json=json.dumps(evidence.detected_via()),
        highlights=[rows[id(c)] for c in top_contributions(evidence.contributions, limit=_HIGHLIGHTS_PER_SKILL)],
    )
