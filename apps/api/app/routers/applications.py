"""HTTP endpoints for the swipe deck, consent receipts and the pipeline board.

Objective 3's client-facing surface: the PWA reads its card deck here, posts each
swipe (right being the affirmative consent action), renders the Kanban board, and
can trigger a recruiter-mailbox sync on demand instead of waiting for the poller.

Every route belongs to the logged-in account. Another account's card answers 404,
never 403, so its existence isn't revealed.
"""

import asyncio
import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload, load_only

from ..applications import repository
from ..applications.board import BOARD_STAGES, is_valid_stage
from ..applications.repository import StageTransitionError
from ..applications.schemas import (
    SubmissionRequest,
    ApplicationCard,
    BoardResponse,
    ConsentReceipt,
    DeckCountResponse,
    DeckResponse,
    MailSyncRequest,
    MailSyncResponse,
    StageChangeRequest,
    SwipeRequest,
    SwipeResponse,
)
from ..auth.deps import get_current_user
from ..auth.models import Account
from ..apply import service as apply_service
from ..config import settings
from ..db import get_db
from ..facts import repository as facts_repository
from ..jobs import matching
from ..jobs import models as job_models
from ..jobs.pipeline import run_discovery_cycle
from ..jobs.repository import get_job_by_id, get_jobs_feed, hydrate_jobs, to_job_contract
from ..jobs.schemas import MatchContract
from ..mail.imap_client import ImapNotConfigured, fetch_recruiter_messages
from ..mail.sync import mailbox_account_id, sync_messages

router = APIRouter(prefix="/api", tags=["applications"], dependencies=[Depends(get_current_user)])


def ranked_deck(db: Session, prefs: dict, min_legitimacy: float, limit: int, seen: set[str]):
    """Every unswiped live job, scored against the preferences; matches first, then the rest.

    Scoring reads only small columns (deal-breakers are checked against the title
    and skill list); ``raw_description`` stays deferred so a deal never hauls every
    job's 20 KB description into memory. Just the returned page is re-fetched.
    """
    rows = (
        db.query(job_models.Job)
        .options(
            load_only(
                job_models.Job.job_id,
                job_models.Job.title,
                job_models.Job.location,
                job_models.Job.is_remote,
                job_models.Job.experience_level,
                job_models.Job.primary_skills_json,
                job_models.Job.posted_at,
                job_models.Job.created_at,
            )
        )
        .filter(job_models.Job.is_active.is_(True), job_models.Job.legitimacy_probability >= min_legitimacy,
                job_models.Job.ghost_score < 700)
        .all()
    )
    scored = []
    for job in rows:
        if job.job_id in seen:
            continue
        cheap_text = f"{job.title} {job.primary_skills_json or ''}"
        points, reasons = matching.score(job, prefs, breaker_text=cheap_text)
        scored.append((points, job.posted_at or job.created_at, job.job_id, reasons))
    scored.sort(key=lambda t: (t[0], t[1] or datetime.datetime.min), reverse=True)
    page = scored[:limit]
    by_id = hydrate_jobs(db, [job_id for _, _, job_id, _ in page])
    out = []
    for points, _, job_id, reasons in page:
        job = by_id.get(job_id)
        if job is None:
            continue
        contract = to_job_contract(job)
        contract.match = MatchContract(score=points, percent=matching.percent(points), reasons=reasons)
        out.append(contract)
    return out, len(scored)


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
    """Ghost-filtered cards the account has not swiped yet, best fit for their preferences first."""
    seen = repository.swiped_job_ids(db, account.id)
    prefs = facts_repository.get_preferences(db, account.id)

    def deal():
        if prefs and prefs.get("roles"):
            return ranked_deck(db, prefs, min_legitimacy, limit, seen)
        return get_jobs_feed(db, min_legitimacy=min_legitimacy, limit=limit, page=1, exclude_job_ids=seen)

    jobs, total = deal()
    # An empty store means discovery has never run; seed the quick feeds and deal again.
    if total == 0 and not seen:
        await run_discovery_cycle(db, limit=20, boards=False)
        jobs, total = deal()

    return DeckResponse(
        candidate_ref=account.ref,
        total=total,
        min_legitimacy=min_legitimacy,
        jobs=jobs,
        swiped_total=len(seen),
    )


@router.get("/applications/deck/count", response_model=DeckCountResponse)
def get_deck_count(
    min_legitimacy: float = Query(default=0.60, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_user),
):
    """The deck's sizes only, counted in SQL - dashboards no longer pull a deck page for a number."""
    seen = repository.swiped_job_ids(db, account.id)
    query = db.query(func.count(job_models.Job.job_id)).filter(
        job_models.Job.is_active.is_(True),
        job_models.Job.legitimacy_probability >= min_legitimacy,
        job_models.Job.ghost_score < 700,
    )
    if seen:
        query = query.filter(~job_models.Job.job_id.in_(seen))
    return DeckCountResponse(total=query.scalar() or 0, swiped_total=len(seen))


@router.post("/applications/swipe", response_model=SwipeResponse)
def swipe(payload: SwipeRequest, db: Session = Depends(get_db), account: Account = Depends(get_current_user)):
    """Record a swipe. Right is the affirmative action and writes a signed consent log.

    A right swipe on a job Hire can fill also queues the fill run on its own, unless
    the account turned "start filling when I swipe right" off. Sending still waits
    for the typed confirmation."""
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

    autofill_started = False
    job_row = db.query(job_models.Job).filter(job_models.Job.job_id == job.job_id).first()
    prefs = facts_repository.get_preferences(db, account.id)
    if direction == "right" and not already and prefs.get("autofill_on_swipe", True):
        if apply_service.start_run(db, app, job_row) is not None:
            autofill_started = True
            db.commit()

    run = apply_service.latest_run(db, account.id, app.application_id) if autofill_started else None
    card = repository.to_card(app, job_row, run)
    return SwipeResponse(application=card, consent=card.consent, already_recorded=already,
                         autofill_started=autofill_started)


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


@router.post("/applications/{application_id}/submission", response_model=ApplicationCard)
def set_submission(application_id: str, payload: SubmissionRequest, db: Session = Depends(get_db),
                   account: Account = Depends(get_current_user)):
    """The candidate applied on the employer's site (or undoes that)."""
    app = repository.get_application(db, application_id, account.id)
    if app is None or app.swipe_direction != "right":
        raise _not_found(application_id)
    return repository.to_card(repository.mark_submitted(db, app, sent=payload.sent))


@router.get("/mail/status")
def mail_status(db: Session = Depends(get_db), account: Account = Depends(get_current_user)) -> dict[str, bool]:
    """Whether this account's recruiter replies are read automatically (a mailbox is set up for it)."""
    connected = bool(settings.imap_enabled and settings.imap_host and settings.imap_user)
    if connected and settings.imap_candidate_ref:
        connected = mailbox_account_id(db) == account.id
    return {"connected": connected}


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
