from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

# GitHub's own login rule: alphanumerics and single inner hyphens, at most 39 characters.
GITHUB_LOGIN_PATTERN = r"^[A-Za-z0-9](?:-?[A-Za-z0-9])*$"


class PowRefreshRequest(BaseModel):
    # Optional once WP1 links the GitHub identity; required until then.
    github_username: Optional[str] = Field(default=None, pattern=GITHUB_LOGIN_PATTERN, max_length=39)
    # Analyse private repos too (needs the user's own GitHub token). Their evidence is
    # stored flagged private and is never returned unless asked for.
    include_private: bool = False


class PowRunOut(BaseModel):
    id: int
    status: str
    progress: int
    github_username: str
    include_private: bool
    sample_coverage: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    profile_id: Optional[int] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class EvidenceOut(BaseModel):
    skill: str
    repo: str
    url: str
    kind: str
    weight: float
    date: Optional[datetime] = None
    summary: str
    is_private: bool


class EvidenceResponse(BaseModel):
    skill: Optional[str] = None
    evidence: list[EvidenceOut]
