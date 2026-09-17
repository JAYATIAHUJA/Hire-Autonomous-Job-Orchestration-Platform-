import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import relationship

from .db import Base

skill_highlights = Table(
    "skill_highlights",
    Base.metadata,
    Column("skill_id", ForeignKey("skills.id"), primary_key=True),
    Column("contribution_id", ForeignKey("contributions.id"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    analysis_mode = Column(String, nullable=False, default="limited")
    timeline_json = Column(Text, nullable=True)
    work_mix_json = Column(Text, nullable=True)

    projects = relationship("Project", back_populates="user", cascade="all, delete-orphan")
    contributions = relationship("Contribution", back_populates="user", cascade="all, delete-orphan")
    skills = relationship("Skill", back_populates="user", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    full_name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    role = Column(String, nullable=False)
    ownership_share = Column(Float, nullable=True)
    is_external = Column(Boolean, default=False)
    contribution_count = Column(Integer, default=0)
    meaningful_lines = Column(Integer, default=0)
    primary_language = Column(String, nullable=True)
    first_contribution = Column(DateTime, nullable=True)
    last_contribution = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="projects")


class Contribution(Base):
    __tablename__ = "contributions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    kind = Column(String, nullable=False)
    repo_full_name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    title = Column(Text, nullable=False)
    type = Column(String, nullable=False)
    date = Column(DateTime, nullable=True)
    meaningful_additions = Column(Integer, default=0)
    meaningful_deletions = Column(Integer, default=0)
    files_touched = Column(Integer, default=0)
    is_external = Column(Boolean, default=False)
    is_bulk = Column(Boolean, default=False)
    weight = Column(Float, default=0.0)
    languages_json = Column(Text, nullable=True)

    user = relationship("User", back_populates="contributions")


class Skill(Base):
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    confidence_tier = Column(String, nullable=False)
    weight = Column(Float, default=0.0)
    lines = Column(Integer, default=0)
    project_count = Column(Integer, default=0)
    contribution_count = Column(Integer, default=0)
    external_pr_count = Column(Integer, default=0)
    active_months = Column(Integer, default=0)
    first_active = Column(DateTime, nullable=True)
    last_active = Column(DateTime, nullable=True)
    factors_json = Column(Text, nullable=False)
    detected_via_json = Column(Text, nullable=False)

    user = relationship("User", back_populates="skills")
    highlights = relationship("Contribution", secondary=skill_highlights, order_by="desc(Contribution.weight)")
