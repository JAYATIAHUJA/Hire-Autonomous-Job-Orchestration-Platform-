from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    username: str
    token: Optional[str] = None


class AnalyzeResponse(BaseModel):
    profile_id: int
    username: str


class ContributionOut(BaseModel):
    kind: str
    repo_full_name: str
    url: str
    title: str
    type: str
    date: Optional[datetime] = None
    meaningful_additions: int
    meaningful_deletions: int
    files_touched: int
    is_external: bool
    is_bulk: bool
    languages: list[str]


class FactorOut(BaseModel):
    label: str
    met: bool
    detail: str


class SkillOut(BaseModel):
    name: str
    confidence_tier: str
    lines: int
    project_count: int
    contribution_count: int
    external_pr_count: int
    active_months: int
    first_active: Optional[datetime] = None
    last_active: Optional[datetime] = None
    factors: list[FactorOut]
    detected_via: list[str]
    highlights: list[ContributionOut]


class ProjectOut(BaseModel):
    full_name: str
    url: str
    role: str
    ownership_share: Optional[float] = None
    is_external: bool
    contribution_count: int
    meaningful_lines: int
    primary_language: Optional[str] = None
    last_contribution: Optional[datetime] = None


class WorkMixOut(BaseModel):
    type: str
    count: int
    lines: int


class TimelinePoint(BaseModel):
    month: str
    commits: int


class ProfileOut(BaseModel):
    profile_id: int
    username: str
    analysis_mode: str
    total_projects: int
    total_commits: int
    analyzed_contributions: int
    meaningful_lines: int
    external_merged_prs: int
    languages: list[str]
    work_mix: list[WorkMixOut]
    timeline: list[TimelinePoint]
    projects: list[ProjectOut]
    top_contributions: list[ContributionOut]
    skills: list[SkillOut]
