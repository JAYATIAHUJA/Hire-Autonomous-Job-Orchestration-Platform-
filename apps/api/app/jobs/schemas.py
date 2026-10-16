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


class JobContract(BaseModel):
    job_id: str
    company: CompanyContract
    role: RoleContract
    ghost_job_metrics: GhostJobMetricsContract
    parsed_requirements: ParsedRequirementsContract
    created_at: str


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
