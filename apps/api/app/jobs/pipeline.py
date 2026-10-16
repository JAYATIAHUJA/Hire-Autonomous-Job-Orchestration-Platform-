"""Ingestion, caching, and Ghost Filtering Pipeline orchestrator."""

import json
from typing import Any, Optional
from sqlalchemy.orm import Session

from .ghost_filter.scorer import score_job
from .ingestion.feeds import fetch_public_feed_jobs
from .ingestion.hasher import compute_description_hash
from .repository import lookup_cache, save_cache_entry, save_job


async def process_and_ingest_job_items(
    db: Session,
    raw_items: list[dict[str, Any]],
) -> dict[str, int]:
    """Process a batch of job items through the hashing, ghost filtering, and storage pipeline.
    
    Returns:
        {"ingested_count": int, "purged_ghost_count": int, "cached_reused_count": int}
    """
    ingested_count = 0
    purged_ghost_count = 0
    cached_reused_count = 0

    for item in raw_items:
        raw_desc = item.get("raw_description", "")
        desc_hash = compute_description_hash(raw_desc)

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
        job_id = item.get("source_id") or f"job_{desc_hash[:10]}"
        save_job(
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
            is_active=is_active,
        )

    return {
        "ingested_count": ingested_count,
        "purged_ghost_count": purged_ghost_count,
        "cached_reused_count": cached_reused_count,
    }


async def run_discovery_cycle(db: Session, limit: int = 20) -> dict[str, int]:
    """Execute a full background discovery cycle from public job feeds."""
    raw_feed_items = await fetch_public_feed_jobs(limit=limit)
    return await process_and_ingest_job_items(db, raw_feed_items)
