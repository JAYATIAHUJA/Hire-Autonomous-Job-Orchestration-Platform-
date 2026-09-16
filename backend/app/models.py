import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    timeline_json = Column(Text, nullable=True)

    repos = relationship("Repo", back_populates="user", cascade="all, delete-orphan")
    skills = relationship("Skill", back_populates="user", cascade="all, delete-orphan")


class Repo(Base):
    __tablename__ = "repos"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    full_name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    primary_language = Column(String, nullable=True)
    is_fork = Column(Boolean, default=False)
    commit_count = Column(Integer, default=0)
    additions = Column(Integer, default=0)
    deletions = Column(Integer, default=0)
    pr_count = Column(Integer, default=0)
    first_contribution = Column(DateTime, nullable=True)
    last_contribution = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="repos")


class Skill(Base):
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    confidence_tier = Column(String, nullable=False)
    commit_count = Column(Integer, default=0)
    repo_count = Column(Integer, default=0)
    pr_count = Column(Integer, default=0)
    first_active = Column(DateTime, nullable=True)
    last_active = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="skills")
    evidence = relationship("SkillEvidence", back_populates="skill", cascade="all, delete-orphan")


class SkillEvidence(Base):
    __tablename__ = "skill_evidence"

    id = Column(Integer, primary_key=True)
    skill_id = Column(Integer, ForeignKey("skills.id"), nullable=False)
    repo_full_name = Column(String, nullable=False)
    repo_url = Column(String, nullable=False)
    commit_count = Column(Integer, default=0)
    pr_count = Column(Integer, default=0)
    sample_commit_url = Column(String, nullable=True)
    sample_commit_message = Column(Text, nullable=True)

    skill = relationship("Skill", back_populates="evidence")
