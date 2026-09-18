"""Pydantic contracts for the swipe deck, consent receipts and the pipeline board."""

from typing import Any, Optional

from pydantic import BaseModel, Field

from ..jobs.schemas import JobContract


class SwipeRequest(BaseModel):
    job_id: str
    direction: str = Field(..., description="'right' records consent and applies, 'left' skips the card")
    candidate_ref: str = Field(..., description="Who is consenting — GitHub handle or email")
    purpose: Optional[str] = Field(default=None, description="Overrides the default consent purpose text")


class ConsentReceipt(BaseModel):
    consent_id: str
    subject: str
    employer_name: str
    purpose: str
    granted_at: str
    algorithm: str
    signature: str
    payload: dict[str, Any]
    verified: bool = Field(..., description="Signature re-checked against the stored payload on read")


class PipelineEventOut(BaseModel):
    from_stage: Optional[str] = None
    to_stage: str
    source: str
    detail: Optional[str] = None
    occurred_at: Optional[str] = None


class ApplicationCard(BaseModel):
    application_id: str
    job_id: str
    candidate_ref: str
    employer_name: str
    employer_domain: Optional[str] = None
    role_title: str
    location: Optional[str] = None
    stage: str
    stage_label: str
    swipe_direction: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_event_summary: Optional[str] = None
    consent: Optional[ConsentReceipt] = None
    events: list[PipelineEventOut] = []


class SwipeResponse(BaseModel):
    application: ApplicationCard
    consent: Optional[ConsentReceipt] = None
    already_recorded: bool = False


class BoardColumn(BaseModel):
    stage: str
    label: str
    count: int
    cards: list[ApplicationCard]


class BoardResponse(BaseModel):
    candidate_ref: str
    total: int
    columns: list[BoardColumn]


class DeckResponse(BaseModel):
    candidate_ref: str
    total: int
    min_legitimacy: float
    jobs: list[JobContract]


class StageChangeRequest(BaseModel):
    to_stage: str
    detail: Optional[str] = None


class RecruiterMessage(BaseModel):
    """A recruiter reply, either read over IMAP or posted in for a dry run."""

    uid: str
    from_address: str = ""
    subject: str = ""
    body: str = ""
    received_at: Optional[str] = None


class MailSyncRequest(BaseModel):
    messages: Optional[list[RecruiterMessage]] = Field(
        default=None,
        description="Supply messages directly to replay a sync without touching a mailbox.",
    )
    limit: int = 25


class MailSyncResponse(BaseModel):
    source: str  # "imap" | "inline"
    fetched: int
    matched: int
    moved: int
    skipped: int
    errors: list[str] = []
    moves: list[dict[str, Any]] = []
