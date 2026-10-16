"""The fact vault: the only grounding set the tailoring engine may state claims from.

Every row is owned by ``account_id`` (WP1's ``accounts.id``) and is erased by
DELETE /v1/profile. ``account_id`` has no FK yet because ``accounts`` lands with WP1.
"""

import datetime
import uuid

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from ..db import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")

FACT_SOURCES = ("resume", "linkedin_pdf", "user_confirmed", "github", "reference")
FACT_STATUSES = ("proposed", "approved", "rejected")


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def new_fact_id() -> str:
    return f"fct_{uuid.uuid4().hex[:20]}"


def new_upload_id() -> str:
    return f"res_{uuid.uuid4().hex[:20]}"


class CandidateProfile(Base):
    """The profile assembled from approved facts, plus preferences. One per account."""

    __tablename__ = "candidate_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, unique=True, index=True)
    data = Column(JSONType, nullable=False, default=dict)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class ProfileVersion(Base):
    """A targeted cut of the master profile: which facts it shows, under which headline.

    ``fact_ids`` lists the experience, project, achievement and skill facts it includes.
    Identity, links and education always come along; a fact deleted from the master
    simply drops out.
    """

    __tablename__ = "profile_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    headline = Column(String, nullable=True)
    target_role = Column(String, nullable=True)
    fact_ids = Column(JSONType, nullable=False, default=list)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class ProfileFact(Base):
    """One atomic claim about the candidate. Untrusted until ``status == "approved"``."""

    __tablename__ = "profile_facts"

    id = Column(String, primary_key=True, default=new_fact_id)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    kind = Column(String, nullable=False, index=True)
    text = Column(Text, nullable=False)
    structured = Column(JSONType, nullable=False, default=dict)
    source = Column(String, nullable=False)  # one of FACT_SOURCES
    source_ref = Column(String, nullable=True)  # e.g. the resume upload id
    inferred = Column(Boolean, nullable=False, default=False)
    status = Column(String, nullable=False, default="proposed", index=True)
    conflict_with_fact_id = Column(String, ForeignKey("profile_facts.id", ondelete="SET NULL"), nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


class AnswerBankEntry(Base):
    """A reusable answer to a common application question (notice period, CTC, ...)."""

    __tablename__ = "answer_bank"
    __table_args__ = (UniqueConstraint("account_id", "key", name="uq_answer_bank_account_key"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    key = Column(String, nullable=False)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class ResumeUpload(Base):
    """A stored resume file: where it lives in the object store and its sha256."""

    __tablename__ = "resume_uploads"

    id = Column(String, primary_key=True, default=new_upload_id)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    object_key = Column(String, nullable=False)
    sha256 = Column(String, nullable=False, index=True)
    content_type = Column(String, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    text_source = Column(String, nullable=False)  # "text_layer" | "pdf_document"
    created_at = Column(DateTime, default=_utcnow)
