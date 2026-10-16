"""HTTP endpoints for background Proof-of-Work runs and the Evidence Index.

Owner-scoped throughout: every route depends on ``get_current_user`` and reads
or writes only that account's rows. Someone else's run is a 404, never a 403.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ..auth.consents import require_github_consent
from ..auth.deps import get_current_user
from ..db import get_db
from ..profiles.pow_models import PowEvidence, PowRun
from ..profiles.pow_schemas import EvidenceOut, EvidenceResponse, PowRefreshRequest, PowRunOut
from ..services import pow_service
from ..services.github_tokens import linked_login
from ..time_utils import to_aware_utc

router = APIRouter(prefix="/v1/profile", tags=["pow"])


@router.post("/pow/refresh", response_model=PowRunOut, status_code=202)
def refresh(response: Response, payload: Optional[PowRefreshRequest] = None,
            account=Depends(require_github_consent),
            db: Session = Depends(get_db)):
    payload = payload or PowRefreshRequest()  # the web client posts no body when GitHub is linked
    linked = linked_login(db, account.id)
    username = payload.github_username or linked
    if not username:
        raise HTTPException(status_code=422, detail="Connect GitHub or give github_username.")
    # Evidence is cited as the user's own work, so once an account has linked GitHub
    # it may only analyse that login.
    if linked and username.lower() != linked.lower():
        raise HTTPException(status_code=422, detail="You can only analyse the GitHub account you connected.")

    run, created = pow_service.request_refresh(db, account.id, username, payload.include_private)
    if not created:
        response.status_code = 200  # an analysis is already queued or running: return it
    return _run_out(run)


@router.get("/pow/runs/{run_id}", response_model=PowRunOut)
def get_run(run_id: int, account=Depends(get_current_user), db: Session = Depends(get_db)):
    run = pow_service.get_run(db, account.id, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    return _run_out(run)


@router.get("/evidence", response_model=EvidenceResponse)
def get_evidence(
    skill: Optional[str] = Query(default=None, max_length=80, description="Skill name, e.g. react or next.js"),
    include_private: bool = Query(default=False, description="Also return evidence from opted-in private repos"),
    limit: int = Query(default=50, ge=1, le=200),
    account=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = pow_service.list_evidence(db, account.id, skill, include_private, limit)
    return EvidenceResponse(skill=skill, evidence=[_evidence_out(r) for r in rows])


@router.delete("/pow", status_code=204)
def erase_pow(account=Depends(get_current_user), db: Session = Depends(get_db)):
    """Erase every PoW run, evidence row and analysed profile this account owns (DPDP)."""
    pow_service.erase(db, account.id)
    return Response(status_code=204)


def _run_out(run: PowRun) -> PowRunOut:
    return PowRunOut(
        id=run.id,
        status=run.status,
        progress=run.progress,
        github_username=run.github_username,
        include_private=run.include_private,
        sample_coverage=run.sample_coverage,
        error=run.error,
        profile_id=run.profile_id,
        created_at=to_aware_utc(run.created_at),
        started_at=to_aware_utc(run.started_at),
        finished_at=to_aware_utc(run.finished_at),
    )


def _evidence_out(e: PowEvidence) -> EvidenceOut:
    return EvidenceOut(skill=e.skill, repo=e.repo, url=e.url, kind=e.kind, weight=e.weight,
                       date=to_aware_utc(e.date), summary=e.summary, is_private=e.is_private)
