"""HTTP for auto-fill: start a run, answer what the form asks, review, confirm, watch."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..applications import repository as app_repo
from ..applications.repository import AUTOFILL_SOURCES
from ..auth.deps import get_current_user
from ..auth.models import Account
from ..db import get_db
from ..facts.storage import ObjectStore, get_object_store
from ..jobs.models import Job
from . import service
from .models import ApplyRun, ApplyRunEvent

router = APIRouter(prefix="/api/applications/{application_id}/autofill", tags=["apply"])


class RunOut(BaseModel):
    id: int
    status: str
    step: Optional[str] = None
    filled: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    error: Optional[str] = None
    has_screenshot: bool = False
    company: str
    role: str


class RunEventOut(BaseModel):
    seq: int
    kind: str
    label: str
    field: Optional[str] = None
    shown: Optional[str] = None
    at: Optional[str] = None


class RunEventsOut(BaseModel):
    run_id: int
    status: str
    step: Optional[str] = None
    events: list[RunEventOut] = []


class AnswersIn(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)


class SubmitIn(BaseModel):
    # The user types the company's name: a real application can't be taken back.
    company_name: str


def _app(db: Session, account: Account, application_id: str):
    app = app_repo.get_application(db, application_id, account.id)
    if app is None or app.swipe_direction != "right":
        raise HTTPException(status_code=404, detail="Application not found.")
    return app


def _latest(db: Session, account: Account, application_id: str) -> Optional[ApplyRun]:
    return service.latest_run(db, account.id, application_id)


def _out(run: ApplyRun, app) -> RunOut:
    return RunOut(id=run.id, status=run.status, step=run.step, filled=list(run.filled or []),
                  missing=list(run.missing or []), error=run.error, has_screenshot=bool(run.screenshot_key),
                  company=app.employer_name, role=app.role_title)


@router.post("", response_model=RunOut, status_code=202)
def start(application_id: str, account: Account = Depends(get_current_user), db: Session = Depends(get_db)):
    """Ask Hire to fill this application. Nothing is submitted until the user confirms."""
    app = _app(db, account, application_id)
    if app.submission_status == "sent":
        raise HTTPException(status_code=409, detail="This application was already sent.")
    job = db.query(Job).filter(Job.job_id == app.job_id).first()
    run = service.start_run(db, app, job)
    if run is None:
        if job is None or job.source not in AUTOFILL_SOURCES or not job.apply_url:
            raise HTTPException(status_code=422, detail="Hire can only fill Greenhouse forms for now. Apply on the company’s site.")
        raise HTTPException(status_code=409, detail="This run can’t be restarted now.")
    db.commit()
    return _out(run, app)


@router.get("", response_model=Optional[RunOut])
def latest(application_id: str, account: Account = Depends(get_current_user), db: Session = Depends(get_db)):
    app = _app(db, account, application_id)
    run = _latest(db, account, application_id)
    return _out(run, app) if run else None


@router.get("/events", response_model=RunEventsOut)
def events(application_id: str, after: int = Query(default=0, ge=0),
           account: Account = Depends(get_current_user), db: Session = Depends(get_db)):
    """The run's visible steps after ``seq`` - one row per thing Hire did, so the sheet
    can follow along instead of polling the whole run."""
    app = _app(db, account, application_id)
    run = _latest(db, account, application_id)
    if run is None:
        raise HTTPException(status_code=404, detail="No run yet.")
    rows = (db.query(ApplyRunEvent).filter(ApplyRunEvent.run_id == run.id, ApplyRunEvent.seq > after)
            .order_by(ApplyRunEvent.seq.asc()).all())
    return RunEventsOut(
        run_id=run.id, status=run.status, step=run.step,
        events=[RunEventOut(seq=e.seq, kind=e.kind, label=e.label, field=e.field_name, shown=e.shown_value,
                            at=e.created_at.isoformat() + "Z" if e.created_at else None) for e in rows],
    )


@router.post("/answers", response_model=RunOut)
def answer(application_id: str, payload: AnswersIn, account: Account = Depends(get_current_user),
           db: Session = Depends(get_db)):
    """Answer the questions the profile couldn't, then fill again.

    Each answer is remembered under its normalised question, so a later form that
    asks the same thing in other words fills itself (never for free-text)."""
    app = _app(db, account, application_id)
    run = _latest(db, account, application_id)
    if run is None or run.status != "needs_answers":
        raise HTTPException(status_code=409, detail="Nothing is waiting for answers.")
    cleaned = {k.strip(): v.strip() for k, v in payload.answers.items() if k.strip() and v and v.strip()}
    run.extra_answers = {**(run.extra_answers or {}), **cleaned}
    run.status, run.step, run.error = "queued", "Waiting for a browser", None
    app.submission_status = "filling"
    for question, value in cleaned.items():
        service.remember_answer(db, account.id, question, value)
        service.emit(db, run, "answered", f"You answered: {question}")
    db.commit()
    return _out(run, app)


@router.post("/submit", response_model=RunOut)
def submit(application_id: str, payload: SubmitIn, account: Account = Depends(get_current_user),
           db: Session = Depends(get_db)):
    """The user reviewed the filled form and confirms sending it."""
    app = _app(db, account, application_id)
    run = _latest(db, account, application_id)
    if run is None or run.status != "ready_to_submit":
        raise HTTPException(status_code=409, detail="Review the filled form first.")
    if payload.company_name.strip().lower() != app.employer_name.strip().lower():
        raise HTTPException(status_code=422, detail=f"Type “{app.employer_name}” exactly to send the application.")
    run.status, run.step = "submit_requested", "Waiting for a browser"
    app.submission_status = "filling"
    db.commit()
    return _out(run, app)


@router.post("/cancel", response_model=RunOut)
def cancel(application_id: str, account: Account = Depends(get_current_user), db: Session = Depends(get_db)):
    app = _app(db, account, application_id)
    run = _latest(db, account, application_id)
    if run is None or run.status in ("submitted", "submitting"):
        raise HTTPException(status_code=409, detail="This run can’t be cancelled now.")
    run.status, run.step = "cancelled", None
    if app.submission_status != "sent":
        app.submission_status = "not_sent"
    db.commit()
    return _out(run, app)


@router.get("/screenshot")
def screenshot(application_id: str, account: Account = Depends(get_current_user), db: Session = Depends(get_db),
               store: Optional[ObjectStore] = Depends(get_object_store)):
    _app(db, account, application_id)
    run = _latest(db, account, application_id)
    if run is None or not run.screenshot_key or store is None:
        raise HTTPException(status_code=404, detail="No screenshot yet.")
    return Response(content=store.get(run.screenshot_key), media_type="image/png",
                    headers={"Cache-Control": "no-store"})
