from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AnalyzeRequest(BaseModel):
    username: str
    token: Optional[str] = None


class AnalyzeResponse(BaseModel):
    profile_id: int
    username: str


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    repo_full_name: str
    repo_url: str
    commit_count: int
    pr_count: int
    sample_commit_url: Optional[str] = None
    sample_commit_message: Optional[str] = None


class SkillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    confidence_tier: str
    commit_count: int
    repo_count: int
    pr_count: int
    first_active: Optional[datetime] = None
    last_active: Optional[datetime] = None
    evidence: list[EvidenceOut]


class RepoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    full_name: str
    url: str
    primary_language: Optional[str] = None
    commit_count: int
    additions: int
    deletions: int
    pr_count: int
    last_contribution: Optional[datetime] = None


class TimelinePoint(BaseModel):
    month: str
    commits: int


class ProfileOut(BaseModel):
    profile_id: int
    username: str
    total_repos: int
    total_commits: int
    total_additions: int
    total_deletions: int
    languages: list[str]
    timeline: list[TimelinePoint]
    repos: list[RepoOut]
    skills: list[SkillOut]
