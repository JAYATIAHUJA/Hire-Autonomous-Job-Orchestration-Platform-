"""SQLAlchemy models for normalized Job entities, Companies, and Global JD Cache."""

import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from ..db import Base


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, index=True)
    domain = Column(String, nullable=True, index=True)
    external_layoff_flag = Column(Boolean, default=False)
    # Public job board, from the ATS registry (app/jobs/ats_registry.py).
    ats_vendor = Column(String, nullable=True)  # greenhouse | lever | ashby
    ats_board_token = Column(String, nullable=True)
    ats_checked_at = Column(DateTime, nullable=True)
    # When the board was last read for openings (oldest first gets read next).
    jobs_fetched_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    jobs = relationship("Job", back_populates="company", cascade="all, delete-orphan")

    __table_args__ = (Index("ix_companies_ats_board", "ats_vendor", "ats_board_token", unique=True),)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, unique=True, nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)

    title = Column(String, nullable=False)
    location = Column(String, nullable=False)
    salary_range = Column(String, nullable=True)

    # Ghost Job metrics
    ghost_score = Column(Integer, nullable=False)  # 0 - 999
    risk_band = Column(String, nullable=False)     # "Low" | "Moderate" | "High"
    legitimacy_probability = Column(Float, nullable=False)
    posting_age_days = Column(Integer, default=0)
    repost_count = Column(Integer, default=0)

    # Parsed requirements
    experience_level = Column(String, default="Entry-Level / Fresher")
    primary_skills_json = Column(Text, nullable=False)  # JSON array of strings
    raw_description_hash = Column(String, nullable=False, index=True)
    raw_description = Column(Text, nullable=True)
    # Same job on several boards -> same key (employer + title + city; see cross_portal_key).
    canonical_key = Column(String, nullable=True, index=True)

    # Where it came from: greenhouse | lever | ashby | remoteok | sample.
    source = Column(String, nullable=True, index=True)
    # The employer's own posting: where the candidate reads and applies.
    apply_url = Column(String, nullable=True)
    posted_at = Column(DateTime, nullable=True)
    # Last time a board still listed it; a job that drops off its board is closed.
    last_seen_at = Column(DateTime, nullable=True)
    is_remote = Column(Boolean, default=False, nullable=False)

    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    company = relationship("Company", back_populates="jobs")


class DiscoveryRun(Base):
    """One pass over the job boards. A ``requested`` row asks the worker to run now."""

    __tablename__ = "discovery_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(String, nullable=False, index=True)  # requested | running | done | failed
    requested_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    boards_checked = Column(Integer, nullable=False, default=0)
    boards_failed = Column(Integer, nullable=False, default=0)
    jobs_added = Column(Integer, nullable=False, default=0)
    jobs_updated = Column(Integer, nullable=False, default=0)
    jobs_closed = Column(Integer, nullable=False, default=0)
    ghosts_filtered = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)


class JobDescriptionCache(Base):
    """Global JD hash cache to prevent duplicate NLP extraction and save LLM token spend."""
    __tablename__ = "jd_cache"

    hash = Column(String, primary_key=True)  # SHA-256 (older rows: MD5)
    parsed_skills_json = Column(Text, nullable=False)
    experience_level = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
