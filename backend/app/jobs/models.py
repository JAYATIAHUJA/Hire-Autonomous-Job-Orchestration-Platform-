"""SQLAlchemy models for normalized Job entities, Companies, and Global JD Cache."""

import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from ..db import Base


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, index=True)
    domain = Column(String, nullable=True, index=True)
    external_layoff_flag = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    jobs = relationship("Job", back_populates="company", cascade="all, delete-orphan")


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

    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    company = relationship("Company", back_populates="jobs")


class JobDescriptionCache(Base):
    """Global JD hash cache to prevent duplicate NLP extraction and save LLM token spend."""
    __tablename__ = "jd_cache"

    hash = Column(String, primary_key=True)  # MD5 or SHA-256
    parsed_skills_json = Column(Text, nullable=False)
    experience_level = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
