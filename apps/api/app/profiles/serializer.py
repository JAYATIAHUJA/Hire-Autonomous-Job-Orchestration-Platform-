"""Turn a stored ``User`` graph into the public API response schemas.

Presentation-only: ordering, aggregation and shaping. No database or business logic.
"""

import json
from typing import Iterable

from .. import models
from ..schemas import ContributionOut, ProfileOut, ProjectOut, SkillOut
from ..time_utils import to_aware_utc

# Confidence tiers, best first — drives the skill ordering shown to the user.
_TIER_ORDER = {"Strong": 0, "Moderate": 1, "Limited": 2}
_TOP_CONTRIBUTIONS = 6


def serialize_profile(user: models.User) -> ProfileOut:
    skills = sorted(user.skills, key=lambda s: (_TIER_ORDER.get(s.confidence_tier, 3), -s.weight))
    projects = sorted(user.projects, key=lambda p: (p.is_external, -p.meaningful_lines))
    ranked = sorted(user.contributions, key=lambda c: (c.is_bulk, -c.weight))

    return ProfileOut(
        profile_id=user.id,
        username=user.username,
        analysis_mode=user.analysis_mode,
        total_projects=len(projects),
        total_commits=sum(p.contribution_count for p in projects if not p.is_external),
        analyzed_contributions=len(user.contributions),
        meaningful_lines=sum(c.meaningful_additions + c.meaningful_deletions for c in user.contributions),
        external_merged_prs=sum(1 for c in user.contributions if c.is_external and c.kind == "pr"),
        languages=_language_ranking(projects),
        work_mix=json.loads(user.work_mix_json or "[]"),
        timeline=json.loads(user.timeline_json or "[]"),
        projects=[_project_out(p) for p in projects],
        top_contributions=[_contribution_out(c) for c in ranked[:_TOP_CONTRIBUTIONS] if c.weight > 0],
        skills=[_skill_out(s) for s in skills],
    )


def _language_ranking(projects: Iterable[models.Project]) -> list[str]:
    lines: dict[str, int] = {}
    for p in projects:
        if p.primary_language:
            lines[p.primary_language] = lines.get(p.primary_language, 0) + p.meaningful_lines
    return sorted(lines, key=lines.get, reverse=True)


def _project_out(p: models.Project) -> ProjectOut:
    return ProjectOut(
        full_name=p.full_name,
        url=p.url,
        role=p.role,
        ownership_share=p.ownership_share,
        is_external=p.is_external,
        contribution_count=p.contribution_count,
        meaningful_lines=p.meaningful_lines,
        primary_language=p.primary_language,
        last_contribution=to_aware_utc(p.last_contribution),
    )


def _contribution_out(c: models.Contribution) -> ContributionOut:
    return ContributionOut(
        kind=c.kind,
        repo_full_name=c.repo_full_name,
        url=c.url,
        title=c.title,
        type=c.type,
        date=to_aware_utc(c.date),
        meaningful_additions=c.meaningful_additions,
        meaningful_deletions=c.meaningful_deletions,
        files_touched=c.files_touched,
        is_external=c.is_external,
        is_bulk=c.is_bulk,
        languages=json.loads(c.languages_json or "[]"),
    )


def _skill_out(s: models.Skill) -> SkillOut:
    return SkillOut(
        name=s.name,
        confidence_tier=s.confidence_tier,
        lines=s.lines,
        project_count=s.project_count,
        contribution_count=s.contribution_count,
        external_pr_count=s.external_pr_count,
        active_months=s.active_months,
        first_active=to_aware_utc(s.first_active),
        last_active=to_aware_utc(s.last_active),
        factors=json.loads(s.factors_json),
        detected_via=json.loads(s.detected_via_json),
        highlights=[_contribution_out(c) for c in s.highlights],
    )
