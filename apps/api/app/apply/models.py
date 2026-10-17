"""Apply runs: Hire filling an employer's application form, step by step, in the open.

A run goes queued -> filling -> ready_to_submit (the user reviews a screenshot and the
filled values) -> submit_requested (the user typed the company name) -> submitting ->
submitted. It stops at needs_answers when a required question has no answer in the
profile (never guessed), and ends at failed / captcha / cancelled otherwise.
"""

import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from ..db import Base
from ..facts.models import JSONType

ACTIVE = ("queued", "filling", "submit_requested", "submitting")
FINAL = ("submitted", "failed", "captcha", "cancelled", "unconfirmed")


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


class ApplyRun(Base):
    __tablename__ = "apply_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    application_id = Column(String, nullable=False, index=True)  # Application.application_id
    job_id = Column(String, nullable=False)
    status = Column(String, nullable=False, default="queued", index=True)
    # What the user sees while it runs: "Opening the form", "Filling 9 fields"...
    step = Column(String, nullable=True)
    # The plan: [{label, shown, source, required}], plus missing required questions.
    filled = Column(JSONType, nullable=False, default=list)
    missing = Column(JSONType, nullable=False, default=list)
    # Answers the user gave for missing questions, keyed by the question label.
    extra_answers = Column(JSONType, nullable=False, default=dict)
    screenshot_key = Column(String, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class ApplyRunEvent(Base):
    """One visible step of a run, in order: what a live progress list shows.

    ``seq`` is gap-free per run so the client can ask for "everything after N".
    """

    __tablename__ = "apply_run_events"
    __table_args__ = (UniqueConstraint("run_id", "seq", name="uq_apply_run_events_run_seq"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("apply_runs.id"), nullable=False, index=True)
    seq = Column(Integer, nullable=False)
    kind = Column(String, nullable=False)  # queued|step|filled|fill_error|needs_answers|ready|sent|captcha|failed
    label = Column(Text, nullable=False)  # the human line: "Filled email", "Ready for your review"...
    field_name = Column(String, nullable=True)
    shown_value = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


class AnswerMemory(Base):
    """One answer the user gave on a form, remembered for later forms.

    Keyed by the normalised question, so the same question asked in other words can
    reuse it. The planner never uses it for free-text questions and, unless the
    wording is identical, for sensitive ones (pay, legal, EEO).
    """

    __tablename__ = "answer_memory"
    __table_args__ = (UniqueConstraint("account_id", "question_norm", name="uq_answer_memory_account_question"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    question_norm = Column(String, nullable=False)
    question_text = Column(Text, nullable=False)  # the wording the user actually answered
    answer = Column(Text, nullable=False)
    uses = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
