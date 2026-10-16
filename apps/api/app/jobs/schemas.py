"""Pydantic schemas adhering strictly to the Shared Data Contract between Student B, C, and A."""

from typing import Any, Optional
from pydantic import BaseModel, Field


class CompanyContract(BaseModel):
    name: str
    domain: Optional[str] = None
    external_layoff_flag: bool = False


class RoleContract(BaseModel):
    title: str
    location: str
    salary_range: Optional[str] = None


class GhostJobMetricsContract(BaseModel):
    ghost_score: int = Field(..., ge=0, le=999, description="Standardized Ghost Score (0-999)")
    risk_band: str = Field(..., description="'Low' (0-399), 'Moderate' (400-699), or 'High' (700-999)")
    legitimacy_probability: float = Field(..., ge=0.0, le=1.0)
    posting_age_days: int = Field(..., ge=0)
    repost_count: int = Field(..., ge=0)


class ParsedRequirementsContract(BaseModel):
    primary_skills: list[str]
    experience_level: str
    raw_description_hash: str


class SourceContract(BaseModel):
    """Where the listing came from and where to read / apply on the employer's side."""

    name: Optional[str] = None  # greenhouse | lever | ashby | remoteok | sample
    apply_url: Optional[str] = None
    posted_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    is_remote: bool = False


class MatchContract(BaseModel):
    """Why a job is in this candidate's deck."""

    score: int = 0
    percent: int = 0  # 0-100, for the card
    reasons: list[str] = []


class JobContract(BaseModel):
    job_id: str
    company: CompanyContract
    role: RoleContract
    ghost_job_metrics: GhostJobMetricsContract
    parsed_requirements: ParsedRequirementsContract
    created_at: str
    source: SourceContract = SourceContract()
    # Full text on GET /jobs/{id}; a short preview in lists and the deck.
    description: Optional[str] = None
    match: Optional[MatchContract] = None


class DiscoveryRunOut(BaseModel):
    id: int
    status: str
    requested_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    boards_checked: int = 0
    boards_failed: int = 0
    jobs_added: int = 0
    jobs_updated: int = 0
    jobs_closed: int = 0
    ghosts_filtered: int = 0


class DiscoveryStatus(BaseModel):
    """How jobs get here, for the "where do these come from?" panel."""

    active_jobs: int
    companies_with_jobs: int
    boards_tracked: int
    by_source: dict[str, int]
    interval_minutes: int
    last_run: Optional[DiscoveryRunOut] = None
    current_run: Optional[DiscoveryRunOut] = None


class JobFeedResponse(BaseModel):
    total: int
    page: int
    limit: int
    min_legitimacy: float
    jobs: list[JobContract]


class CacheCheckRequest(BaseModel):
    raw_description: Optional[str] = None
    hash: Optional[str] = None


class CacheCheckResponse(BaseModel):
    cached: bool
    hash: str
    job_id: Optional[str] = None
    job: Optional[JobContract] = None


class ScoreJobRequest(BaseModel):
    posting_age_days: int = 0
    repost_count: int = 0
    raw_description: str
    salary_range: Optional[str] = None
    company_name: str = ""
    company_domain: Optional[str] = None
    external_layoff_flag: Optional[bool] = None


class ScoreJobResponse(BaseModel):
    ghost_score: int
    risk_band: str
    legitimacy_probability: float
    is_ghost: bool
    posting_age_days: int
    repost_count: int
    features: dict[str, Any]


class IngestResponse(BaseModel):
    status: str
    ingested_count: int
    purged_ghost_count: int
    cached_reused_count: int
    duplicate_count: int = 0  # same job already stored from another board
