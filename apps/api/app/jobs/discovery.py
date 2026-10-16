"""Discovery runs: when the job boards were last read, and "find jobs now" requests.

The worker owns the reading (it takes minutes). The API only records a ``requested``
run; the worker claims it within ``discovery_poll_seconds``, or starts a scheduled
run once ``discovery_interval_seconds`` have passed since the last one.
"""

import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from .models import Company, DiscoveryRun, Job
from .schemas import DiscoveryRunOut, DiscoveryStatus

# A run still "running" after this long died with its worker.
STALE_AFTER = datetime.timedelta(minutes=30)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def _iso(value: Optional[datetime.datetime]) -> Optional[str]:
    return value.replace(tzinfo=datetime.timezone.utc).isoformat() if value else None


def run_out(run: Optional[DiscoveryRun]) -> Optional[DiscoveryRunOut]:
    if run is None:
        return None
    return DiscoveryRunOut(
        id=run.id, status=run.status, requested_at=_iso(run.requested_at), started_at=_iso(run.started_at),
        finished_at=_iso(run.finished_at), boards_checked=run.boards_checked or 0,
        boards_failed=run.boards_failed or 0, jobs_added=run.jobs_added or 0, jobs_updated=run.jobs_updated or 0,
        jobs_closed=run.jobs_closed or 0, ghosts_filtered=run.ghosts_filtered or 0,
    )


def _pending(db: Session) -> Optional[DiscoveryRun]:
    return (
        db.query(DiscoveryRun)
        .filter(DiscoveryRun.status.in_(("requested", "running")))
        .order_by(DiscoveryRun.id.desc())
        .first()
    )


def status(db: Session) -> DiscoveryStatus:
    active = db.query(Job).filter(Job.is_active.is_(True))
    # Group on the bare column: Postgres treats two coalesce(..., 'unknown') calls with
    # separate bind parameters as different expressions and rejects the GROUP BY.
    by_source: dict[str, int] = {}
    for source, n in db.query(Job.source, func.count(Job.id)).filter(Job.is_active.is_(True)).group_by(Job.source):
        key = source or "unknown"
        by_source[key] = by_source.get(key, 0) + n
    last = (
        db.query(DiscoveryRun)
        .filter(DiscoveryRun.status.in_(("done", "failed")))
        .order_by(DiscoveryRun.finished_at.desc().nullslast(), DiscoveryRun.id.desc())
        .first()
    )
    return DiscoveryStatus(
        active_jobs=active.count(),
        companies_with_jobs=active.with_entities(func.count(func.distinct(Job.company_id))).scalar() or 0,
        boards_tracked=db.query(Company).filter(Company.ats_vendor.isnot(None)).count(),
        by_source=by_source,
        interval_minutes=max(1, settings.discovery_interval_seconds // 60),
        last_run=run_out(last),
        current_run=run_out(_pending(db)),
    )


def request_run(db: Session) -> DiscoveryRun:
    """Queue a run unless one is already queued or running."""
    pending = _pending(db)
    if pending is not None:
        return pending
    run = DiscoveryRun(status="requested", requested_at=_now())
    db.add(run)
    db.commit()
    return run


def claim_run(db: Session) -> Optional[DiscoveryRun]:
    """The run the worker should do now: a request, or a scheduled one that is due."""
    now = _now()
    for stale in db.query(DiscoveryRun).filter(DiscoveryRun.status == "running").all():
        if stale.started_at and now - stale.started_at > STALE_AFTER:
            stale.status, stale.finished_at, stale.error = "failed", now, "worker stopped mid-run"
    run = db.query(DiscoveryRun).filter(DiscoveryRun.status == "requested").order_by(DiscoveryRun.id).first()
    if run is None:
        if db.query(DiscoveryRun).filter(DiscoveryRun.status == "running").first():
            db.commit()
            return None
        last = db.query(func.max(DiscoveryRun.started_at)).scalar()
        if last and now - last < datetime.timedelta(seconds=settings.discovery_interval_seconds):
            db.commit()
            return None
        run = DiscoveryRun(status="requested")
        db.add(run)
    run.status, run.started_at = "running", now
    db.commit()
    return run


def finish_run(db: Session, run: DiscoveryRun, stats: Optional[dict] = None, error: Optional[str] = None) -> None:
    run.finished_at = _now()
    run.status = "failed" if error else "done"
    run.error = error
    for key in ("boards_checked", "boards_failed", "jobs_added", "jobs_updated", "jobs_closed", "ghosts_filtered"):
        if stats and key in stats:
            setattr(run, key, stats[key])
    db.commit()
