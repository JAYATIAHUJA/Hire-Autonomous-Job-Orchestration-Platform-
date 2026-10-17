"""The worker side of apply runs: build the applicant from the account, plan the form,
fill it in a browser, and submit only after the user has confirmed.

Two passes, so nothing is ever sent unreviewed:
  queued -> fill (dry run) -> ready_to_submit   (screenshot + values for the user)
  submit_requested -> fill again and submit -> submitted / captcha / unconfirmed / failed
"""

import logging
import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

import httpx
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, sessionmaker

from ..applications import repository as app_repo
from ..applications.models import Application
from ..auth.models import Account
from ..facts import repository as facts_repo
from ..facts.models import ResumeUpload
from ..facts.storage import ObjectStore
from ..jobs.models import Job
from . import service
from .browser import FormResult, run_form
from .greenhouse import Applicant, parse_job_url, plan_application, remembered_match
from .models import AnswerMemory, ApplyRun

logger = logging.getLogger("hire.apply")

SchemaFetcher = Callable[[str], dict[str, Any]]
FormRunner = Callable[..., FormResult]

# Answer-bank keys -> how forms ask, and how to say the answer. The patterns are
# deliberately loose: real forms word these in many orders ("How soon you can join
# us?", "Notice period (days)", "Earliest start date").
_TOPICS: list[tuple[str, str]] = [
    ("notice_period", r"notice period|how soon|earliest (start|joining|availability)|when can you (join|start)"),
    ("current_ctc", r"current .*?(ctc|salary|compensation|pay|base)"),
    ("expected_ctc", r"expected .*?(ctc|salary|compensation|pay|base)|salary expectation"),
    ("willing_to_relocate", r"relocat"),
    ("work_authorisation_india", r"(authori[sz]ed|eligible|legally allowed) to work( in india)?"),
    ("needs_sponsorship_abroad", r"sponsorship|require (a )?visa|need (a )?visa"),
    ("country_of_residence", r"country of residence|where do you (currently )?live|current country"),
    ("preferred_location", r"preferred location|preffered location|preferred city|location preference"),
]
_SPOKEN = {"immediate": "Immediately", "15_days": "15 days", "30_days": "30 days", "60_days": "60 days",
           "90_days": "90 days", "over_90_days": "More than 90 days", "yes": "Yes", "no": "No", "depends": "Depends"}


def fetch_schema(questions_url: str) -> dict[str, Any]:
    resp = httpx.get(questions_url, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Couldn't read the form ({resp.status_code}). Is the job still open?")
    return resp.json()


def build_applicant(db: Session, account: Account, store: Optional[ObjectStore], workdir: Path,
                    extra_answers: dict[str, Any]) -> Applicant:
    """Everything a form asks, from the account's own approved profile."""
    from ..auth.presence import read_presence

    doc = facts_repo.refresh_profile(db, account.id).data or {}
    ident = doc.get("identity") or {}
    full = ((ident.get("name") or {}).get("value") or account.display_name or "").strip()
    if "@" in full:
        full = ""
    first, _, last = full.partition(" ")
    presence = read_presence(db, account)

    resume_path = ""
    upload = (db.query(ResumeUpload).filter(ResumeUpload.account_id == account.id)
              .order_by(ResumeUpload.created_at.desc()).first())
    if upload is not None and store is not None:
        ext = ".docx" if "word" in upload.content_type else ".pdf"
        path = workdir / f"resume{ext}"
        path.write_bytes(store.get(upload.object_key))
        resume_path = str(path)

    bank = {e.key: e.value for e in facts_repo.get_answer_bank(db, account.id)}
    topics = {pattern: _SPOKEN.get(bank[key], bank[key]) for key, pattern in _TOPICS if bank.get(key)}
    remembered = {m.question_norm: m.answer
                  for m in db.query(AnswerMemory).filter(AnswerMemory.account_id == account.id).all()}

    return Applicant(
        first_name=first.strip(), last_name=last.strip(),
        email=((ident.get("email") or {}).get("value") or account.email or "").strip(),
        phone=((ident.get("phone") or {}).get("value") or "").strip(),
        city=((ident.get("location") or {}).get("value") or "").strip(),
        linkedin=presence.linkedin or "",
        github=f"https://github.com/{presence.github_username}" if presence.github_username else "",
        website=presence.website or presence.portfolio or "",
        resume_path=resume_path,
        answers=dict(extra_answers or {}),
        topic_answers=topics,
        remembered=remembered,
    )


def _claim(db: Session) -> Optional[ApplyRun]:
    # A run claimed but left "filling" by a crash would wait forever: after five
    # quiet minutes it is fair game for another attempt.
    stale_before = datetime.now() - timedelta(minutes=5)
    run = (
        db.query(ApplyRun)
        .filter(
            or_(
                ApplyRun.status.in_(("queued", "submit_requested")),
                and_(ApplyRun.status.in_(("filling", "submitting")), ApplyRun.updated_at < stale_before),
            )
        )
        .order_by(ApplyRun.updated_at.asc())
        .first()
    )
    if run is None:
        return None
    if run.status == "submitting":
        # A submit that died mid-flight is never replayed blind: back to the queue,
        # it re-fills and lands on the user's review again.
        run.status, run.step = "queued", "Waiting for a browser"
        service.emit(db, run, "step", "Requeued: the send was interrupted before we could confirm it")
        db.commit()
        return None
    run.status = "submitting" if run.status == "submit_requested" else "filling"
    run.step = "Reading the application form"
    service.emit(db, run, "step", "Reading the application form")
    db.commit()
    return run


def _set_app(db: Session, run: ApplyRun, status: str) -> Optional[Application]:
    app = db.query(Application).filter(Application.application_id == run.application_id,
                                       Application.account_id == run.account_id).first()
    if app is not None and app.submission_status != "sent":
        app.submission_status = status
    return app


def process_next(session_factory: sessionmaker, store: Optional[ObjectStore],
                 schema_fetcher: SchemaFetcher = fetch_schema, form_runner: FormRunner = run_form) -> Optional[int]:
    """Do one step of one run. Returns the run id, or None when nothing is waiting."""
    db = session_factory()
    try:
        run = _claim(db)
        if run is None:
            return None
        submitting = run.status == "submitting"
        try:
            _advance(db, run, store, submitting, schema_fetcher, form_runner)
        except Exception as exc:  # noqa: BLE001 - a failed run is shown to the user, not raised
            logger.exception("apply run %s failed", run.id)
            db.rollback()
            run.status, run.error, run.step = "failed", str(exc)[:500], None
            _set_app(db, run, "failed")
            db.commit()
        return run.id
    finally:
        db.close()


def _advance(db: Session, run: ApplyRun, store: Optional[ObjectStore], submitting: bool,
             schema_fetcher: SchemaFetcher, form_runner: FormRunner) -> None:
    job = db.query(Job).filter(Job.job_id == run.job_id).first()
    account = db.get(Account, run.account_id)
    if job is None or not job.apply_url:
        raise RuntimeError("This job no longer has an application form.")
    ref = parse_job_url(job.apply_url, job_id=job.job_id)

    with tempfile.TemporaryDirectory() as tmp:
        applicant = build_applicant(db, account, store, Path(tmp), run.extra_answers or {})
        problems = [p for p in applicant.problems() if "not found" not in p]
        if problems:
            run.status, run.step = "needs_answers", None
            run.error = "Add your " + ", ".join(re.sub(r"^profile is missing ", "", p) for p in problems) + " to your profile."
            run.missing = []
            service.emit(db, run, "needs_answers", "Your profile is missing the basics")
            _set_app(db, run, "needs_review")
            db.commit()
            return

        plan = plan_application(ref, schema_fetcher(ref.questions_url), applicant)
        run.filled = [{"label": a.label, "shown": a.shown, "source": a.source, "required": a.required}
                      for a in plan.answers]
        run.missing = list(plan.missing) + [{"label": u, "field": None, "type": "unsupported", "options": []}
                                            for u in plan.unsupported]
        for a in plan.answers:  # a remembered answer was worth saving; note the reuse
            if a.source == "remembered":
                matched = remembered_match(applicant.remembered, a.label)
                if matched:
                    db.query(AnswerMemory).filter(
                        AnswerMemory.account_id == account.id, AnswerMemory.question_norm == matched[0]
                    ).update({AnswerMemory.uses: AnswerMemory.uses + 1}, synchronize_session=False)
        if not plan.ready:
            run.status, run.step = "needs_answers", None
            run.error = None
            for m in run.missing:
                service.emit(db, run, "missing", f"Needs your answer: {m['label']}")
            _set_app(db, run, "needs_review")
            db.commit()
            return

        run.step = "Submitting your application" if submitting else f"Filling {len(plan.answers)} fields"
        service.emit(db, run, "step", run.step)
        db.commit()

        def on_action(answer, ok, problem=""):
            if ok:
                what = (f"Uploaded {answer.shown}" if answer.field_type == "input_file"
                        else f"Chose {answer.shown}" if answer.field_type.startswith("multi_value")
                        else f"Filled {answer.label}")
                service.emit(db, run, "filled", what, field=answer.field_name, shown=answer.shown)
            else:
                service.emit(db, run, "fill_error", f"Couldn't fill {answer.label}: {problem}",
                             field=answer.field_name)

        def on_screenshot(png: bytes):
            if store is not None:
                key = f"apply-runs/{run.account_id}/{run.id}-live.png"
                store.put(key, png, "image/png")
                run.screenshot_key = key

        result = form_runner(ref.form_url, plan.answers, submit=submitting, on_action=on_action,
                             screenshot_every=4, on_screenshot=on_screenshot)

    if result.screenshot and store is not None:
        key = f"apply-runs/{run.account_id}/{run.id}-{'after' if submitting else 'filled'}.png"
        store.put(key, result.screenshot, "image/png")
        run.screenshot_key = key

    run.step = None
    if result.status == "filled":
        run.status, run.error = "ready_to_submit", None
        service.emit(db, run, "ready", "Ready for your review")
        _set_app(db, run, "needs_review")
    elif result.status == "submitted":
        run.status, run.error = "submitted", None
        service.emit(db, run, "sent", "Application sent")
        app = db.query(Application).filter(Application.application_id == run.application_id,
                                           Application.account_id == run.account_id).first()
        db.commit()
        if app is not None:  # records the event, the time and that Hire sent it
            app_repo.mark_submitted(db, app, sent=True, method="auto",
                                    detail="Hire filled and submitted the application after you confirmed.")
    else:
        run.status = {"captcha": "captcha", "unconfirmed": "unconfirmed"}.get(result.status, "failed")
        run.error = "; ".join(result.errors) or result.status
        service.emit(db, run, run.status, run.error)
        _set_app(db, run, "failed")
    db.commit()
