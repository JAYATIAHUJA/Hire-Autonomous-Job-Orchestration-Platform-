"""Ingestion, caching, and Ghost Filtering Pipeline orchestrator."""

import datetime
import json
import logging
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..config import settings
from . import models
from .ats_registry import load_registry
from .ingestion.ats_boards import fetch_boards

from .ghost_filter.scorer import score_job
from .ingestion.feeds import fetch_public_feed_jobs
from .ingestion.canonical_key import cross_portal_key
from .ingestion.hasher import compute_description_hash
from .repository import find_cross_portal_duplicate, lookup_cache, save_cache_entry, save_job


async def process_and_ingest_job_items(
    db: Session,
    raw_items: list[dict[str, Any]],
) -> dict[str, int]:
    """Process a batch of job items through the hashing, ghost filtering, and storage pipeline.
    
    Returns:
        {"ingested_count": int, "purged_ghost_count": int, "cached_reused_count": int,
         "duplicate_count": int, "created_count": int}
    """
    created_count = 0
    ingested_count = 0
    purged_ghost_count = 0
    cached_reused_count = 0
    duplicate_count = 0

    for item in raw_items:
        raw_desc = item.get("raw_description", "")
        desc_hash = compute_description_hash(raw_desc)
        job_id = item.get("source_id") or f"job_{desc_hash[:10]}"
        canonical_key = cross_portal_key(
            item.get("company_name", ""), item.get("title", ""), item.get("location")
        )

        # 0. The same job already came in from another board: keep the first copy.
        if find_cross_portal_duplicate(db, canonical_key, exclude_job_id=job_id):
            duplicate_count += 1
            continue

        # 1. Global JD Cache check (Token saving optimization)
        cache_entry = lookup_cache(db, desc_hash)
        if cache_entry:
            cached_reused_count += 1
            primary_skills = json.loads(cache_entry.parsed_skills_json)
            experience_level = cache_entry.experience_level
        else:
            primary_skills = item.get("primary_skills", [])
            experience_level = item.get("experience_level", "Entry-Level / Fresher")

        # 2. Algorithmic Ghost Job Scoring
        score_res = score_job(
            posting_age_days=item.get("posting_age_days", 0),
            repost_count=item.get("repost_count", 0),
            raw_description=raw_desc,
            salary_range=item.get("salary_range"),
            company_name=item.get("company_name", ""),
            company_domain=item.get("company_domain"),
            external_layoff_flag=item.get("external_layoff_flag"),
        )

        # If primary_skills was empty, use skills detected by feature extractor
        if not primary_skills and score_res.features.detected_skills:
            primary_skills = [s.title() for s in score_res.features.detected_skills]

        # Update global cache if new
        if not cache_entry:
            save_cache_entry(db, desc_hash, primary_skills, experience_level)

        # 3. Execution Rule: Purge or deactivate if ghost score in 700 - 999 band
        is_ghost = score_res.is_ghost
        if is_ghost:
            purged_ghost_count += 1
            is_active = False
        else:
            ingested_count += 1
            is_active = True

        # 4. Save normalized entity to database
        saved = save_job(
            db,
            job_id=job_id,
            company_name=item.get("company_name", "Unknown Co"),
            company_domain=item.get("company_domain"),
            external_layoff_flag=bool(item.get("external_layoff_flag")),
            title=item.get("title", "Software Engineer"),
            location=item.get("location", "Remote"),
            salary_range=item.get("salary_range"),
            ghost_score=score_res.ghost_score,
            risk_band=score_res.risk_band,
            legitimacy_probability=score_res.legitimacy_probability,
            posting_age_days=score_res.features.raw_age_days,
            repost_count=score_res.features.raw_repost_count,
            experience_level=experience_level,
            primary_skills=primary_skills,
            raw_description_hash=desc_hash,
            raw_description=raw_desc,
            canonical_key=canonical_key,
            is_active=is_active,
            source=item.get("source"),
            apply_url=item.get("apply_url"),
            posted_at=item.get("posted_at"),
            is_remote=bool(item.get("is_remote")),
        )
        # "Created" counts live jobs only; a ghost saved switched-off is in purged_ghost_count.
        if getattr(saved, "_was_created", False) and is_active:
            created_count += 1

    return {
        "created_count": created_count,
        "ingested_count": ingested_count,
        "purged_ghost_count": purged_ghost_count,
        "cached_reused_count": cached_reused_count,
        "duplicate_count": duplicate_count,
    }


logger = logging.getLogger("hire.discovery")


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def ensure_registry_loaded(db: Session) -> int:
    """Load the verified board list into ``companies`` the first time. Returns boards known."""
    known = db.query(models.Company).filter(models.Company.ats_vendor.isnot(None)).count()
    if known:
        return known
    path = Path(settings.ats_registry_path)
    if not path.exists():
        logger.warning("ATS registry not found at %s; only feeds will be read", path)
        return 0
    stats = load_registry(db, json.loads(path.read_text(encoding="utf-8")))
    db.commit()
    logger.info("loaded ATS registry: %s", stats)
    return db.query(models.Company).filter(models.Company.ats_vendor.isnot(None)).count()


def _boards_to_read(db: Session, count: int) -> list[models.Company]:
    """Never-read boards first, then the ones read longest ago."""
    return (
        db.query(models.Company)
        .filter(models.Company.ats_vendor.isnot(None), models.Company.ats_board_token.isnot(None))
        .order_by(models.Company.jobs_fetched_at.is_(None).desc(), models.Company.jobs_fetched_at.asc(),
                  models.Company.id.asc())
        .limit(count)
        .all()
    )


async def read_ats_boards(db: Session, run: Optional[models.DiscoveryRun] = None) -> dict[str, int]:
    """Read the next batch of employer boards and ingest their tech openings."""
    totals = {"boards_checked": 0, "boards_failed": 0, "created": 0, "updated": 0, "closed": 0, "ghosts": 0}
    ensure_registry_loaded(db)
    companies = _boards_to_read(db, settings.ats_boards_per_round)
    if not companies:
        return totals
    results = await fetch_boards([(c.ats_vendor, c.ats_board_token, c.name, c.domain) for c in companies])
    now = _now()
    for company, result in zip(companies, results):
        totals["boards_checked"] += 1
        company.jobs_fetched_at = now
        if not result.ok:
            totals["boards_failed"] += 1
            logger.info("board %s:%s failed: %s", company.ats_vendor, company.ats_board_token, result.error)
            db.commit()
            continue
        stats = await process_and_ingest_job_items(db, result.items)
        totals["created"] += stats["created_count"]
        totals["updated"] += stats["ingested_count"] - stats["created_count"]
        totals["ghosts"] += stats["purged_ghost_count"]
        # A job the board no longer lists has closed: take it out of every deck.
        open_jobs = (
            db.query(models.Job)
            .filter(models.Job.company_id == company.id, models.Job.source == company.ats_vendor,
                    models.Job.is_active.is_(True))
            .all()
        )
        closed = [job for job in open_jobs if job.job_id not in result.seen_ids]
        for job in closed:
            job.is_active = False
        totals["closed"] += len(closed)
        db.commit()
        if run is not None:  # live progress for the "finding jobs" screen
            run.boards_checked = totals["boards_checked"]
            run.jobs_added = totals["created"]
            db.commit()
    return totals


def close_ineligible(db: Session) -> int:
    """Switch off stored board jobs an applicant in India cannot take (e.g. remote in Zurich only)."""
    from .ats_registry import is_india_location
    from .ingestion.ats_boards import remote_open_to_india

    closed = 0
    for job in db.query(models.Job).filter(models.Job.is_active.is_(True),
                                           models.Job.source.in_(("greenhouse", "lever", "ashby"))):
        if is_india_location(job.location):
            continue
        if not remote_open_to_india([job.location] if job.location else []):
            job.is_active = False
            closed += 1
    db.commit()
    return closed


async def run_discovery_cycle(db: Session, limit: int = 20, run: Optional[models.DiscoveryRun] = None,
                              boards: bool = True) -> dict[str, int]:
    """One discovery round: employer boards, then RemoteOK (if on), then demo jobs (if on).

    The hard-coded sample jobs only come in when ``demo_jobs_enabled`` is set (tests);
    otherwise any left from Phase 0 are switched off so nobody swipes a fake job.
    """
    totals = (await read_ats_boards(db, run) if boards else
              {"boards_checked": 0, "boards_failed": 0, "created": 0, "updated": 0, "closed": 0, "ghosts": 0})
    feed_items = await fetch_public_feed_jobs(limit=limit)
    feed = await process_and_ingest_job_items(db, feed_items)
    remoteok_ids = {i["source_id"] for i in feed_items if i.get("source") == "remoteok"}
    if remoteok_ids:  # the feed answered: anything it no longer lists (or we now filter out) closes
        db.query(models.Job).filter(models.Job.source == "remoteok", models.Job.is_active.is_(True),
                                    models.Job.job_id.notin_(remoteok_ids)).update(
            {models.Job.is_active: False}, synchronize_session=False)
        db.commit()
    close_ineligible(db)
    if not settings.demo_jobs_enabled:
        db.query(models.Job).filter(models.Job.source == "sample", models.Job.is_active.is_(True)).update(
            {models.Job.is_active: False}, synchronize_session=False)
        db.commit()
    return {
        **feed,
        "boards_checked": totals["boards_checked"],
        "boards_failed": totals["boards_failed"],
        "jobs_added": totals["created"] + feed["created_count"],
        "jobs_updated": totals["updated"] + feed["ingested_count"] - feed["created_count"],
        "jobs_closed": totals["closed"],
        "ghosts_filtered": totals["ghosts"] + feed["purged_ghost_count"],
    }
