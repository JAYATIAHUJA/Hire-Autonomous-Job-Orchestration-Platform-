"""Proof-of-Work background runs and the Evidence Index.

``account_id`` is the WP1 login account. It is an indexed integer without a
foreign key for now: the ``accounts`` table arrives with WP1 (migration 0003),
and the FK is added in a follow-up migration once both are on phase-0.
"""

import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, text

from ..db import Base

RUN_QUEUED, RUN_RUNNING, RUN_DONE, RUN_FAILED = "queued", "running", "done", "failed"
ACTIVE_STATUSES = (RUN_QUEUED, RUN_RUNNING)
EVIDENCE_KINDS = ("commit", "pr", "repo", "file")

_ACTIVE_WHERE = text("status IN ('queued', 'running')")


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


class PowRun(Base):
    """One GitHub analysis for one account, executed by the worker."""

    __tablename__ = "pow_runs"
    # At most one queued/running run per account. The service checks first; this
    # partial unique index makes it true even when two refreshes race.
    __table_args__ = (
        Index("uq_pow_runs_one_active_per_account", "account_id", unique=True,
              postgresql_where=_ACTIVE_WHERE, sqlite_where=_ACTIVE_WHERE),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, nullable=False, index=True)
    github_username = Column(String, nullable=False)
    status = Column(String, nullable=False, default=RUN_QUEUED, index=True)
    progress = Column(Integer, nullable=False, default=0)
    include_private = Column(Boolean, nullable=False, default=False)
    token_source = Column(String, nullable=True)  # "user" | "app" | "none"
    # {"sampled_commits": 640, "total_commits": 2100, ...} — see fetch_service.
    sample_coverage = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    profile_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)


class PowEvidence(Base):
    """One citeable piece of evidence that an account has a skill.

    ``url`` is a real github.com link (commit, pull request or repository) taken
    from the GitHub API, so the tailoring engine can cite it. Rows from private
    repos exist only when the user opted in and carry ``is_private``; they are
    never returned unless explicitly asked for.
    """

    __tablename__ = "pow_evidence"
    __table_args__ = (Index("ix_pow_evidence_account_skill", "account_id", "skill_key"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, nullable=False, index=True)
    run_id = Column(Integer, ForeignKey("pow_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    skill = Column(String, nullable=False)
    skill_key = Column(String, nullable=False)  # normalised for lookup: "Next.js" -> "nextjs"
    repo = Column(String, nullable=False)
    url = Column(String, nullable=False)
    kind = Column(String, nullable=False)  # commit | pr | repo | file
    weight = Column(Float, nullable=False, default=0.0)
    date = Column(DateTime, nullable=True)
    summary = Column(Text, nullable=False)
    is_private = Column(Boolean, nullable=False, default=False)
