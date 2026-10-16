"""HTTP endpoints for the swipe deck, consent receipts and the pipeline board.

Objective 3's client-facing surface: the PWA reads its card deck here, posts each
swipe (right being the affirmative consent action), renders the Kanban board, and
can trigger a recruiter-mailbox sync on demand instead of waiting for the poller.

Every route belongs to the logged-in account. Another account's card answers 404,
never 403, so its existence isn't revealed.
"""

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..applications import repository
from ..applications.board import BOARD_STAGES, is_valid_stage
from ..applications.repository import StageTransitionError
from ..applications.schemas import (
    ApplicationCard,
    BoardResponse,
    ConsentReceipt,
    DeckResponse,
    MailSyncRequest,
    MailSyncResponse,
    StageChangeRequest,
    SwipeRequest,
    SwipeResponse,
)
from ..auth.deps import get_current_user
from ..auth.models import Account
from ..config import settings
from ..db import get_db
from ..jobs.pipeline import run_discovery_cycle
from ..jobs.repository import get_job_by_id, get_jobs_feed
from ..mail.imap_client import ImapNotConfigured, fetch_recruiter_messages
from ..mail.sync import mailbox_account_id, sync_messages

router = APIRouter(prefix="/api", tags=["applications"], dependencies=[Depends(get_current_user)])


def _not_found(application_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Application '{application_id}' not found.")


@router.get("/applications/deck", response_model=DeckResponse)
async def get_deck(
    candidate_ref: Optional[str] = Query(default=None, description="Deprecated and ignored"),
    limit: int = Query(default=20, ge=1, le=100),
    min_legitimacy: float = Query(default=0.60, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_user),
):
    """Ghost-filtered cards the account has not swiped yet, safest listings first."""
    seen = repository.swiped_job_ids(db, account.id)
    jobs, total = get_jobs_feed(
        db, min_legitimacy=min_legitimacy, limit=limit, page=1, exclude_job_ids=seen
    )

    # An empty store means discovery has never run; seed it and deal again.
    if total == 0 and not seen:
        await run_discovery_cycle(db, limit=20)
        jobs, total = get_jobs_feed(
            db, min_legitimacy=min_legitimacy, limit=limit, page=1, exclude_job_ids=seen
        )

    return DeckResponse(
        candidate_ref=account.ref,
        total=total,
        min_legitimacy=min_legitimacy,
        jobs=jobs,
    )


@router.post("/applications/swipe", response_model=SwipeResponse)
def swipe(payload: SwipeRequest, db: Session = Depends(get_db), account: Account = Depends(get_current_user)):
    """Record a swipe. Right is the affirmative action and writes a signed consent log."""
    direction = payload.direction.strip().lower()
    if direction not in {"left", "right"}:
        raise HTTPException(status_code=422, detail="Direction must be 'left' or 'right'.")

    job = get_job_by_id(db, payload.job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{payload.job_id}' not found.")

    app, already = repository.record_swipe(
        db,
        account_id=account.id,
        candidate_ref=account.ref,
        job_id=job.job_id,
        direction=direction,
        employer_name=job.company.name,
        employer_domain=job.company.domain,
        role_title=job.role.title,
        location=job.role.location,
        purpose=payload.purpose,
    )

    card = repository.to_card(app)
    return SwipeResponse(application=card, consent=card.consent, already_recorded=already)


@router.get("/applications/board", response_model=BoardResponse)
def get_board(
    candidate_ref: Optional[str] = Query(default=None, description="Deprecated and ignored"),
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_user),
):
    """The account's Kanban board: Applied, Interview Scheduled, Rejected."""
    return repository.get_board(db, account.id, account.ref)


@router.get("/applications/{application_id}", response_model=ApplicationCard)
def get_application(
    application_id: str, db: Session = Depends(get_db), account: Account = Depends(get_current_user)
):
    app = repository.get_application(db, application_id, account.id)
    if not app:
        raise _not_found(application_id)
    return repository.to_card(app)


@router.get("/applications/{application_id}/consent", response_model=ConsentReceipt)
def get_consent(
    application_id: str, db: Session = Depends(get_db), account: Account = Depends(get_current_user)
):
    """The signed consent receipt, re-verified against its signature on read."""
    app = repository.get_application(db, application_id, account.id)
    if not app:
        raise _not_found(application_id)

    receipt = repository.to_consent_receipt(app.consent)
    if not receipt:
        raise HTTPException(
            status_code=404,
            detail=f"No consent was recorded for '{application_id}' - the card was swiped left.",
        )
    return receipt


@router.post("/applications/{application_id}/stage", response_model=ApplicationCard)
def change_stage(
    application_id: str,
    payload: StageChangeRequest,
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_user),
):
    """Move a card by hand, for when the candidate hears back outside the mailbox."""
    app = repository.get_application(db, application_id, account.id)
    if not app:
        raise _not_found(application_id)

    to_stage = payload.to_stage.strip().lower()
    if not is_valid_stage(to_stage) or to_stage not in BOARD_STAGES:
        raise HTTPException(
            status_code=422, detail="to_stage must be one of: " + ", ".join(BOARD_STAGES)
        )

    try:
        app = repository.move_stage(
            db, app, to_stage, source="manual", detail=payload.detail or "Moved by the candidate."
        )
    except StageTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return repository.to_card(app)


@router.post("/mail/sync", response_model=MailSyncResponse)
async def trigger_mail_sync(
    payload: MailSyncRequest, db: Session = Depends(get_db), account: Account = Depends(get_current_user)
):
    """Run a recruiter-reply sync now, for the logged-in account's board only.

    With no body, reads the configured IMAP mailbox - only if it is this account's.
    Posting ``messages`` replays a batch of replies instead, which is how the demo
    (and the tests) drive the board without a live inbox.
    """
    if payload.messages:
        stats = sync_messages(db, [m.model_dump() for m in payload.messages], account_id=account.id)
        return MailSyncResponse(source="inline", **stats)

    # The server mailbox belongs to one account; nobody else may read or apply it.
    if settings.imap_candidate_ref and mailbox_account_id(db) != account.id:
        raise HTTPException(status_code=404, detail="No mailbox is configured for this account.")

    try:
        messages = await asyncio.to_thread(fetch_recruiter_messages, None, payload.limit)
    except ImapNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:  # noqa: BLE001 - surface mailbox failures to the caller
        raise HTTPException(status_code=502, detail=f"Mailbox read failed: {exc}")

    return MailSyncResponse(source="imap", **sync_messages(db, messages, account_id=account.id))
