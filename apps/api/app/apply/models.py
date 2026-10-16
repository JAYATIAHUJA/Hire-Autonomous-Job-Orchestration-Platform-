"""Apply runs: Hire filling an employer's application form, step by step, in the open.

A run goes queued -> filling -> ready_to_submit (the user reviews a screenshot and the
filled values) -> submit_requested (the user typed the company name) -> submitting ->
submitted. It stops at needs_answers when a required question has no answer in the
profile (never guessed), and ends at failed / captcha / cancelled otherwise.
"""

import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

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
