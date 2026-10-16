"""Proof-of-Work runs: queue, claim, execute, and read back the Evidence Index.

Queue is the ``pow_runs`` table itself (DB polling, ADR-007's Postgres
``FOR UPDATE SKIP LOCKED`` pattern), so a refresh survives API restarts and needs
no extra infrastructure. The worker (``python -m app.worker``) claims one queued
run at a time and executes it here.
"""

import datetime
import logging
from typing import Callable, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .. import models
from ..config import settings
from ..github_client import GitHubAPIError, GitHubClient
from ..profiles import builder, repository
from ..profiles.evidence import build_evidence, skill_key
from ..profiles.pow_models import (
    ACTIVE_STATUSES,
    RUN_DONE,
    RUN_FAILED,
    RUN_QUEUED,
    RUN_RUNNING,
    PowEvidence,
    PowRun,
)
from .fetch_service import fetch_contributions
from .github_tokens import resolve_token

logger = logging.getLogger("hire.pow")

# Builds the GitHub client for a run; tests swap in one backed by fixtures.
ClientFactory = Callable[[Optional[str]], GitHubClient]


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


# --- queue -------------------------------------------------------------------------------

def active_run(db: Session, account_id: int) -> Optional[PowRun]:
    return (
        db.query(PowRun)
        .filter(PowRun.account_id == account_id, PowRun.status.in_(ACTIVE_STATUSES))
        .order_by(PowRun.id.desc())
        .first()
    )


def request_refresh(db: Session, account_id: int, github_username: str, include_private: bool) -> tuple[PowRun, bool]:
    """Queue a run, or return the account's queued/running one. (run, created)."""
    sweep_stale(db)
    if existing := active_run(db, account_id):
        return existing, False
    run = PowRun(account_id=account_id, github_username=github_username, include_private=include_private,
                 status=RUN_QUEUED, progress=0)
    db.add(run)
    try:
        db.commit()
    except IntegrityError:  # a concurrent refresh won the partial unique index
        db.rollback()
        return active_run(db, account_id), False
    return run, True


def get_run(db: Session, account_id: int, run_id: int) -> Optional[PowRun]:
    """Owner-scoped: someone else's run is indistinguishable from a missing one."""
    return db.query(PowRun).filter(PowRun.id == run_id, PowRun.account_id == account_id).first()


def sweep_stale(db: Session) -> int:
    """Fail runs whose worker died mid-run, so they stop blocking new refreshes.
    They are not replayed automatically (ADR-007); the user refreshes again."""
    cutoff = _now() - datetime.timedelta(seconds=settings.pow_stale_run_seconds)
    stale = db.query(PowRun).filter(PowRun.status == RUN_RUNNING, PowRun.started_at < cutoff).all()
    for run in stale:
        run.status, run.finished_at = RUN_FAILED, _now()
        run.error = "Interrupted: the analysis stopped before finishing. Refresh to try again."
    if stale:
        db.commit()
    return len(stale)


def claim_next(db: Session) -> Optional[PowRun]:
    """Move the oldest queued run to running. SKIP LOCKED lets several workers share the queue."""
    run = (
        db.query(PowRun)
        .filter(PowRun.status == RUN_QUEUED)
        .order_by(PowRun.id)
        .with_for_update(skip_locked=True)
        .first()
    )
    if run is None:
        db.rollback()
        return None
    run.status, run.started_at, run.progress = RUN_RUNNING, _now(), 1
    db.commit()
    return run


# --- execution ---------------------------------------------------------------------------

async def execute(db: Session, run: PowRun, client_factory: Optional[ClientFactory] = None) -> PowRun:
    token, run.token_source = resolve_token(db, run.account_id)
    db.commit()

    def progress(percent: int) -> None:
        percent = min(int(percent), 99)
        if percent > run.progress:
            run.progress = percent
            db.commit()

    try:
        client = (client_factory or (lambda t: GitHubClient(token=t)))(token)
        data = await fetch_contributions(run.github_username, token, client=client,
                                         include_private=run.include_private, progress=progress)
        if not data["projects"]:
            raise _RunFailed("No non-fork repositories or merged pull requests found.")
        user = repository.save(db, builder.build_profile(run.github_username, _public_only(data)))
        _replace_evidence(db, run, data["contributions"])
    except (GitHubAPIError, _RunFailed) as e:
        db.rollback()
        return _finish(db, run, RUN_FAILED, error=_error_message(e, run.github_username))
    except Exception:  # noqa: BLE001 - never leave a run stuck in "running"
        db.rollback()
        logger.exception("pow run %s failed", run.id)
        return _finish(db, run, RUN_FAILED, error="Analysis failed unexpectedly. Refresh to try again.")

    _drop_superseded_profiles(db, run.account_id, keep=user.id)
    run.profile_id = user.id
    run.sample_coverage = data["sample_coverage"]
    return _finish(db, run, RUN_DONE)


async def process_next(session_factory: sessionmaker, client_factory: Optional[ClientFactory] = None) -> Optional[int]:
    """Worker step: claim and execute one queued run. Returns its id, or None if the queue was empty."""
    db = session_factory()
    try:
        sweep_stale(db)
        run = claim_next(db)
        if run is None:
            return None
        await execute(db, run, client_factory)
        return run.id
    finally:
        db.close()


class _RunFailed(Exception):
    pass


def _finish(db: Session, run: PowRun, status: str, error: Optional[str] = None) -> PowRun:
    run.status, run.error, run.finished_at = status, error, _now()
    if status == RUN_DONE:
        run.progress = 100
    db.commit()
    return run


def _error_message(e: Exception, username: str) -> str:
    if isinstance(e, GitHubAPIError):
        if e.rate_limited:
            return "GitHub rate limit reached. Try again later or connect your GitHub account."
        if e.status_code == 404:
            return f"GitHub user '{username}' not found."
        if e.status_code == 401:
            return "GitHub rejected the token. Reconnect your GitHub account."
        return "GitHub API error. Try again later."
    return str(e)


def _public_only(data: dict) -> dict:
    """The legacy profile (``users``) is served publicly: never put private-repo work in it."""
    private = data.get("private_repos") or set()
    return {
        **data,
        "projects": [p for p in data["projects"] if p["full_name"] not in private],
        "contributions": [c for c in data["contributions"] if not c.private],
    }


def _drop_superseded_profiles(db: Session, account_id: int, keep: int) -> None:
    """Keep only the newest analysis per account (data minimisation): older runs lose their profile."""
    older = db.query(PowRun).filter(PowRun.account_id == account_id, PowRun.profile_id.isnot(None),
                                    PowRun.profile_id != keep).all()
    ids = {r.profile_id for r in older}
    for r in older:
        r.profile_id = None
    for user in db.query(models.User).filter(models.User.id.in_(ids)).all():
        db.delete(user)


def _replace_evidence(db: Session, run: PowRun, contributions) -> None:
    db.query(PowEvidence).filter(PowEvidence.account_id == run.account_id).delete(synchronize_session=False)
    db.add_all(PowEvidence(account_id=run.account_id, run_id=run.id, **row) for row in build_evidence(contributions))


# --- reads and erasure -------------------------------------------------------------------

def list_evidence(db: Session, account_id: int, skill: Optional[str], include_private: bool, limit: int) -> list[PowEvidence]:
    q = db.query(PowEvidence).filter(PowEvidence.account_id == account_id)
    if skill:
        q = q.filter(PowEvidence.skill_key == skill_key(skill))
    if not include_private:
        q = q.filter(PowEvidence.is_private.is_(False))
    return q.order_by(PowEvidence.weight.desc(), PowEvidence.id).limit(limit).all()


def erase(db: Session, account_id: int) -> None:
    """DPDP erasure of everything PoW holds for an account: evidence, runs and the profiles they built."""
    runs = db.query(PowRun).filter(PowRun.account_id == account_id).all()
    profile_ids = {r.profile_id for r in runs if r.profile_id}
    db.query(PowEvidence).filter(PowEvidence.account_id == account_id).delete(synchronize_session=False)
    for run in runs:
        db.delete(run)
    db.flush()
    for user in db.query(models.User).filter(models.User.id.in_(profile_ids)).all():
        db.delete(user)  # cascades to projects, contributions, skills
    db.commit()
