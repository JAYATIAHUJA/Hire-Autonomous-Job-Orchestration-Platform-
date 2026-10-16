"""Public, logged-out endpoints: only aggregate numbers for the landing page, nothing personal."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..jobs.models import Company, DiscoveryRun, Job

router = APIRouter(prefix="/v1/public", tags=["public"])


class PublicStats(BaseModel):
    live_jobs: int
    companies_hiring: int
    boards_tracked: int
    ghosts_filtered: int


@router.get("/stats", response_model=PublicStats)
def stats(db: Session = Depends(get_db)):
    live = db.query(Job).filter(Job.is_active.is_(True))
    return PublicStats(
        live_jobs=live.count(),
        companies_hiring=live.with_entities(func.count(func.distinct(Job.company_id))).scalar() or 0,
        boards_tracked=db.query(Company).filter(Company.ats_vendor.isnot(None)).count(),
        ghosts_filtered=db.query(func.coalesce(func.sum(DiscoveryRun.ghosts_filtered), 0)).scalar() or 0,
    )
