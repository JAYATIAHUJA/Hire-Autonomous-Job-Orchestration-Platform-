"""Database repository layer for Job, Company, and JD Cache operations."""

import json
from datetime import datetime, timezone
from typing import Iterable, Optional
from sqlalchemy.orm import Session, joinedload

from . import models
from .schemas import (
    CompanyContract,
    GhostJobMetricsContract,
    JobContract,
    ParsedRequirementsContract,
    RoleContract,
)


def to_job_contract(job: models.Job) -> JobContract:
    """Serialize a Job ORM model to the shared JSON Data Contract."""
    skills = json.loads(job.primary_skills_json or "[]")
    created_str = job.created_at.replace(tzinfo=timezone.utc).isoformat() if job.created_at else datetime.now(timezone.utc).isoformat()

    return JobContract(
        job_id=job.job_id,
        company=CompanyContract(
            name=job.company.name if job.company else "Unknown Company",
            domain=job.company.domain if job.company else None,
            external_layoff_flag=job.company.external_layoff_flag if job.company else False,
        ),
        role=RoleContract(
            title=job.title,
            location=job.location,
            salary_range=job.salary_range,
        ),
        ghost_job_metrics=GhostJobMetricsContract(
            ghost_score=job.ghost_score,
            risk_band=job.risk_band,
            legitimacy_probability=job.legitimacy_probability,
            posting_age_days=job.posting_age_days,
            repost_count=job.repost_count,
        ),
        parsed_requirements=ParsedRequirementsContract(
            primary_skills=skills,
            experience_level=job.experience_level,
            raw_description_hash=job.raw_description_hash,
        ),
        created_at=created_str,
    )


def get_job_by_id(db: Session, job_id: str) -> Optional[JobContract]:
    """Retrieve full job entity by its external unique job_id."""
    job = (
        db.query(models.Job)
        .options(joinedload(models.Job.company))
        .filter(models.Job.job_id == job_id)
        .first()
    )
    return to_job_contract(job) if job else None


def get_job_by_description_hash(db: Session, hash_val: str) -> Optional[JobContract]:
    """Retrieve the job a cached description hash belongs to, if one is stored."""
    job = (
        db.query(models.Job)
        .options(joinedload(models.Job.company))
        .filter(models.Job.raw_description_hash == hash_val)
        .order_by(models.Job.created_at.desc())
        .first()
    )
    return to_job_contract(job) if job else None


def get_jobs_feed(
    db: Session,
    min_legitimacy: float = 0.60,
    limit: int = 20,
    page: int = 1,
    exclude_job_ids: Optional[Iterable[str]] = None,
) -> tuple[list[JobContract], int]:
    """Retrieve clean, ghost-filtered jobs feed for Student C's swipe UI.
    
    Filters out listings with legitimacy below min_legitimacy (purges ghost_score >= 700).
    ``exclude_job_ids`` drops jobs the caller has already dealt with, in SQL, so the
    swipe deck still comes back a full page long however much the candidate has swiped.
    """
    offset = max(0, (page - 1) * limit)
    query = (
        db.query(models.Job)
        .options(joinedload(models.Job.company))
        .filter(
            models.Job.is_active == True,
            models.Job.legitimacy_probability >= min_legitimacy,
            models.Job.ghost_score < 700,
        )
        .order_by(models.Job.ghost_score.asc(), models.Job.created_at.desc())
    )

    excluded = set(exclude_job_ids or ())
    if excluded:
        query = query.filter(~models.Job.job_id.in_(excluded))

    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    return [to_job_contract(j) for j in rows], total


def lookup_cache(db: Session, hash_val: str) -> Optional[models.JobDescriptionCache]:
    """Check if normalized JD hash exists in global cache."""
    return db.query(models.JobDescriptionCache).filter(models.JobDescriptionCache.hash == hash_val).first()


def save_cache_entry(
    db: Session,
    hash_val: str,
    skills: list[str],
    experience_level: str,
) -> models.JobDescriptionCache:
    """Save or update cache entry for JD hash."""
    entry = lookup_cache(db, hash_val)
    if not entry:
        entry = models.JobDescriptionCache(
            hash=hash_val,
            parsed_skills_json=json.dumps(skills),
            experience_level=experience_level,
        )
        db.add(entry)
        db.commit()
    return entry


def save_job(
    db: Session,
    *,
    job_id: str,
    company_name: str,
    company_domain: Optional[str],
    external_layoff_flag: bool,
    title: str,
    location: str,
    salary_range: Optional[str],
    ghost_score: int,
    risk_band: str,
    legitimacy_probability: float,
    posting_age_days: int,
    repost_count: int,
    experience_level: str,
    primary_skills: list[str],
    raw_description_hash: str,
    raw_description: str,
    is_active: bool = True,
) -> models.Job:
    """Upsert Company and Job entities."""
    # Lookup or create company
    company = db.query(models.Company).filter(models.Company.name == company_name).first()
    if not company:
        company = models.Company(
            name=company_name,
            domain=company_domain,
            external_layoff_flag=external_layoff_flag,
        )
        db.add(company)
        db.flush()
    else:
        if external_layoff_flag:
            company.external_layoff_flag = True

    # Lookup or create job
    job = db.query(models.Job).filter(models.Job.job_id == job_id).first()
    if not job:
        job = models.Job(
            job_id=job_id,
            company_id=company.id,
            title=title,
            location=location,
            salary_range=salary_range,
            ghost_score=ghost_score,
            risk_band=risk_band,
            legitimacy_probability=legitimacy_probability,
            posting_age_days=posting_age_days,
            repost_count=repost_count,
            experience_level=experience_level,
            primary_skills_json=json.dumps(primary_skills),
            raw_description_hash=raw_description_hash,
            raw_description=raw_description,
            is_active=is_active,
        )
        db.add(job)
    else:
        job.title = title
        job.location = location
        job.salary_range = salary_range
        job.ghost_score = ghost_score
        job.risk_band = risk_band
        job.legitimacy_probability = legitimacy_probability
        job.posting_age_days = posting_age_days
        job.repost_count = repost_count
        job.primary_skills_json = json.dumps(primary_skills)
        job.is_active = is_active

    db.commit()
    db.refresh(job)
    return job
