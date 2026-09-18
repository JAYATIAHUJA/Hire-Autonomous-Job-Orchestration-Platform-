"""SQLAlchemy models for applications, signed consent receipts and pipeline events."""

import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from ..db import Base
from .board import STAGE_APPLIED


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class Application(Base):
    """One card on the pipeline board: a candidate's swipe on a single job."""

    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    application_id = Column(String, unique=True, nullable=False, index=True)
    candidate_ref = Column(String, nullable=False, index=True)
    job_id = Column(String, nullable=False, index=True)

    employer_name = Column(String, nullable=False, index=True)
    employer_domain = Column(String, nullable=True, index=True)
    role_title = Column(String, nullable=False)
    location = Column(String, nullable=True)

    stage = Column(String, nullable=False, default=STAGE_APPLIED, index=True)
    swipe_direction = Column(String, nullable=False)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    last_event_summary = Column(Text, nullable=True)

    consent = relationship(
        "ConsentLog", back_populates="application", uselist=False, cascade="all, delete-orphan"
    )
    events = relationship(
        "PipelineEvent",
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="PipelineEvent.occurred_at",
    )


class ConsentLog(Base):
    """Immutable signed receipt written when a candidate swipes right."""

    __tablename__ = "consent_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    consent_id = Column(String, unique=True, nullable=False, index=True)
    application_db_id = Column(Integer, ForeignKey("applications.id"), nullable=False)

    subject = Column(String, nullable=False)
    employer_name = Column(String, nullable=False)
    purpose = Column(Text, nullable=False)
    granted_at = Column(String, nullable=False)  # ISO-8601 UTC, exactly as signed

    payload_json = Column(Text, nullable=False)
    signature = Column(String, nullable=False)
    algorithm = Column(String, nullable=False)

    application = relationship("Application", back_populates="consent")


class PipelineEvent(Base):
    """Audit trail of every stage move, whether swiped, dragged or mail-driven."""

    __tablename__ = "pipeline_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    application_db_id = Column(Integer, ForeignKey("applications.id"), nullable=False)

    from_stage = Column(String, nullable=True)
    to_stage = Column(String, nullable=False)
    source = Column(String, nullable=False)  # "swipe" | "imap" | "manual"
    detail = Column(Text, nullable=True)
    message_uid = Column(String, nullable=True, index=True)
    occurred_at = Column(DateTime, default=_utcnow)

    application = relationship("Application", back_populates="events")


class ProcessedMessage(Base):
    """Recruiter mails already consumed, so an IMAP re-poll never double-moves a card."""

    __tablename__ = "processed_messages"

    message_uid = Column(String, primary_key=True)
    classification = Column(String, nullable=False)
    matched_application_id = Column(String, nullable=True)
    subject = Column(Text, nullable=True)
    from_address = Column(String, nullable=True)
    processed_at = Column(DateTime, default=_utcnow)
