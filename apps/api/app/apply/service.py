"""Starting apply runs and recording their visible steps.

Shared by the manual route (``POST .../autofill``), the swipe auto-start and the
worker, so they all queue runs and write events the same way.
"""

from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..applications import models as app_models
from ..applications.repository import AUTOFILL_SOURCES
from ..jobs.models import Job
from .greenhouse import _norm
from .models import ACTIVE, AnswerMemory, ApplyRun, ApplyRunEvent


def latest_run(db: Session, account_id: int, application_id: str) -> Optional[ApplyRun]:
    return (db.query(ApplyRun).filter(ApplyRun.account_id == account_id, ApplyRun.application_id == application_id)
            .order_by(ApplyRun.id.desc()).first())


def start_run(db: Session, app: app_models.Application, job: Optional[Job] = None) -> Optional[ApplyRun]:
    """Queue a fill run for a right-swiped application Hire can fill.

    Returns None (and changes nothing) when the job isn't auto-fillable or was
    already sent; the existing run when one is already live. The caller commits.
    """
    if app.swipe_direction != "right" or app.submission_status == "sent":
        return None
    if job is None:
        job = object_session_query(db, app.job_id)
    if job is None or job.source not in AUTOFILL_SOURCES or not job.apply_url:
        return None
    run = latest_run(db, app.account_id, app.application_id)
    if run is not None and run.status in ACTIVE + ("needs_answers", "ready_to_submit"):
        return run
    run = ApplyRun(account_id=app.account_id, application_id=app.application_id, job_id=app.job_id,
                   status="queued", step="Waiting for a browser", filled=[], missing=[], extra_answers={})
    db.add(run)
    db.flush()
    app.submission_status = "filling"
    emit(db, run, "queued", f"Started filling {app.employer_name}'s form")
    return run


def object_session_query(db: Session, job_id: str) -> Optional[Job]:
    return db.query(Job).filter(Job.job_id == job_id).first()


def emit(db: Session, run: ApplyRun, kind: str, label: str, *, field: Optional[str] = None,
         shown: Optional[str] = None) -> None:
    """Append one visible step. Committed with the run's next commit.

    The flush matters: the app's sessions don't autoflush, so without it every
    event of one transaction would read the same ``max(seq)`` and collide.
    """
    db.flush()
    last = db.query(func.max(ApplyRunEvent.seq)).filter(ApplyRunEvent.run_id == run.id).scalar() or 0
    db.add(ApplyRunEvent(run_id=run.id, seq=last + 1, kind=kind, label=label, field_name=field, shown_value=shown))


def remember_answer(db: Session, account_id: int, question: str, answer: str) -> None:
    """Save (or refresh) a user answer under the normalised question, for later forms."""
    norm = _norm(question)
    if not norm or not answer.strip():
        return
    row = (db.query(AnswerMemory).filter(AnswerMemory.account_id == account_id,
                                         AnswerMemory.question_norm == norm).first())
    if row is None:
        db.add(AnswerMemory(account_id=account_id, question_norm=norm, question_text=question.strip(),
                            answer=answer.strip()))
    else:
        row.question_text, row.answer = question.strip(), answer.strip()
