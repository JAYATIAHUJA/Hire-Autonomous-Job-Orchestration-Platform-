"""Pydantic contracts for the swipe deck, consent receipts and the pipeline board."""

from typing import Any, Optional

from pydantic import BaseModel, Field

from ..jobs.schemas import JobContract


class SwipeRequest(BaseModel):
    job_id: str
    direction: str = Field(..., description="'right' records consent and applies, 'left' skips the card")
    candidate_ref: Optional[str] = Field(
        default=None,
        description="Deprecated and ignored: the consenting candidate is always the logged-in account.",
    )
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
    submission_status: str = "not_sent"
    submitted_at: Optional[str] = None
    submit_method: Optional[str] = None
    # The employer's posting, where the candidate applies; and whether Hire can fill it.
    apply_url: Optional[str] = None
    can_autofill: bool = False


class SubmissionRequest(BaseModel):
    """The candidate says they sent (or did not, after all, send) the application."""

    sent: bool = True


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
    # Jobs this account has already swiped either way (for "applied / passed" counts).
    swiped_total: int = 0


class StageChangeRequest(BaseModel):
    to_stage: str
    detail: Optional[str] = None


class RecruiterMessage(BaseModel):
    """A recruiter reply, either read over IMAP or posted in for a dry run."""

    uid: str
    message_id: Optional[str] = None
    from_address: str = ""
    subject: str = ""
    body: str = ""
    received_at: Optional[str] = None


class MailSyncRequest(BaseModel):
    messages: Optional[list[RecruiterMessage]] = Field(
        default=None,
        description="Supply messages directly to replay a sync without touching a mailbox.",
    )
    candidate_ref: Optional[str] = Field(
        default=None,
        description="Deprecated and ignored: replies only ever move the logged-in account's board.",
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
