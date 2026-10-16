"""Database repository layer for Job, Company, and JD Cache operations."""

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from . import models
from .schemas import (
    CompanyContract,
    GhostJobMetricsContract,
    JobContract,
    ParsedRequirementsContract,
    MatchContract,
    RoleContract,
    SourceContract,
)


def _readable(text: Optional[str], limit: Optional[int]) -> Optional[str]:
    """Plain text for the client even if an older row stored HTML or mis-decoded quotes."""
    from .ingestion.ats_boards import fix_mojibake, plain_text

    if not text:
        return None
    clean = plain_text(text) if "<" in text or "&lt;" in text else fix_mojibake(text)
    return (clean[:limit] if limit else clean) or None


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def to_job_contract(job: models.Job, full_description: bool = False) -> JobContract:
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
        source=SourceContract(
            name=job.source,
            apply_url=job.apply_url,
            posted_at=_iso(job.posted_at),
            last_seen_at=_iso(job.last_seen_at),
            is_remote=bool(job.is_remote),
        ),
        description=_readable(job.raw_description, None if full_description else 400),
    )


def get_job_by_id(db: Session, job_id: str) -> Optional[JobContract]:
    """Retrieve full job entity by its external unique job_id."""
    job = (
        db.query(models.Job)
        .options(joinedload(models.Job.company))
        .filter(models.Job.job_id == job_id)
        .first()
    )
    return to_job_contract(job, full_description=True) if job else None


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
    q: Optional[str] = None,
    city: Optional[str] = None,
    remote: bool = False,
    newest_first: bool = False,
    levels: Optional[Iterable[str]] = None,
    salary_shown: bool = False,
    posted_within_days: Optional[int] = None,
    rank: Optional[Any] = None,
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
    )
    if q and q.strip():
        like = f"%{q.strip()}%"
        query = query.join(models.Company).filter(
            models.Job.title.ilike(like) | models.Company.name.ilike(like) | models.Job.primary_skills_json.ilike(like)
        )
    if city and city.strip():
        query = query.filter(models.Job.location.ilike(f"%{city.strip()}%"))
    if remote:
        query = query.filter(models.Job.is_remote.is_(True) | models.Job.location.ilike("%remote%"))
    if levels:
        query = query.filter(models.Job.experience_level.in_(list(levels)))
    if salary_shown:
        query = query.filter(models.Job.salary_range.isnot(None), models.Job.salary_range != "")
    if posted_within_days:
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=posted_within_days)
        query = query.filter(func.coalesce(models.Job.posted_at, models.Job.created_at) >= since)
    if rank is not None:
        # Best match first: score every match in Python (a few thousand rows at most).
        scored = sorted(((rank(job), job) for job in query.all()),
                        key=lambda t: (t[0][0], t[1].posted_at or t[1].created_at or datetime.min), reverse=True)
        total = len(scored)
        out = []
        for (points, reasons), job in scored[offset:offset + limit]:
            contract = to_job_contract(job)
            contract.match = MatchContract(score=points, percent=max(0, min(100, round(points / 7 * 100))), reasons=reasons)
            out.append(contract)
        return out, total
    if newest_first:
        query = query.order_by(models.Job.posted_at.desc().nullslast(), models.Job.created_at.desc())
    else:
        query = query.order_by(models.Job.ghost_score.asc(), models.Job.created_at.desc())

    excluded = set(exclude_job_ids or ())
    if excluded:
        query = query.filter(~models.Job.job_id.in_(excluded))

    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    return [to_job_contract(j) for j in rows], total


def find_cross_portal_duplicate(
    db: Session, canonical_key: str, *, exclude_job_id: str
) -> Optional[models.Job]:
    """An already-stored copy of this job from a different source, if any."""
    return (
        db.query(models.Job)
        .filter(models.Job.canonical_key == canonical_key, models.Job.job_id != exclude_job_id)
        .first()
    )


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
    canonical_key: Optional[str] = None,
    is_active: bool = True,
    source: Optional[str] = None,
    apply_url: Optional[str] = None,
    posted_at: Optional[datetime] = None,
    is_remote: bool = False,
    commit: bool = True,
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
            canonical_key=canonical_key,
            is_active=is_active,
        )
        db.add(job)
        created = True
    else:
        created = False
        job.title = title
        job.location = location
        job.salary_range = salary_range
        job.ghost_score = ghost_score
        job.risk_band = risk_band
        job.legitimacy_probability = legitimacy_probability
        job.posting_age_days = posting_age_days
        job.repost_count = repost_count
        job.primary_skills_json = json.dumps(primary_skills)
        if canonical_key:
            job.canonical_key = canonical_key
        job.is_active = is_active
        job.raw_description = raw_description
        job.raw_description_hash = raw_description_hash
        job.experience_level = experience_level

    job.source = source or job.source
    job.apply_url = apply_url or job.apply_url
    job.posted_at = posted_at.replace(tzinfo=None) if posted_at else job.posted_at
    job.is_remote = bool(is_remote)
    job.last_seen_at = datetime.now(timezone.utc).replace(tzinfo=None)
    job._was_created = created  # read by the pipeline counters; not a column

    if commit:
        db.commit()
        db.refresh(job)
    else:
        db.flush()
    return job
