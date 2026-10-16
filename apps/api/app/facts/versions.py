"""Profile versions: the master profile, cut for one kind of role.

A user with a backend resume and a data resume keeps one master profile (everything,
built once) and two versions that each show the roles, pointers, projects and skills
that fit. Outreach and applications use a version when one is chosen.
"""

import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth.deps import Account, get_current_user
from ..db import get_db
from . import repository
from .models import ProfileFact, ProfileVersion

router = APIRouter(prefix="/v1/profile/versions", tags=["facts"])

MAX_VERSIONS = 8
# The kinds a version chooses between; the rest (identity, links, education...) always come.
CHOSEN_KINDS = ("experience", "achievement", "project", "skill", "certification")


class VersionIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    headline: Optional[str] = Field(default=None, max_length=160)
    target_role: Optional[str] = Field(default=None, max_length=80)
    fact_ids: list[str] = Field(default_factory=list, max_length=400)


class VersionOut(VersionIn):
    id: int
    updated_at: Optional[datetime.datetime] = None


def _out(v: ProfileVersion) -> VersionOut:
    return VersionOut(id=v.id, name=v.name, headline=v.headline, target_role=v.target_role,
                      fact_ids=list(v.fact_ids or []), updated_at=v.updated_at)


def _owned(db: Session, account_id: int, version_id: int) -> ProfileVersion:
    v = db.query(ProfileVersion).filter(ProfileVersion.id == version_id, ProfileVersion.account_id == account_id).first()
    if v is None:
        raise HTTPException(status_code=404, detail="Version not found.")
    return v


def _valid_ids(db: Session, account_id: int, ids: list[str]) -> list[str]:
    """Keep only the account's own approved facts of the kinds a version chooses."""
    if not ids:
        return []
    rows = db.query(ProfileFact.id).filter(
        ProfileFact.account_id == account_id, ProfileFact.id.in_(ids), ProfileFact.status == "approved",
        ProfileFact.kind.in_(CHOSEN_KINDS),
    ).all()
    allowed = {r[0] for r in rows}
    return [i for i in dict.fromkeys(ids) if i in allowed]


def version_document(db: Session, account_id: int, version: ProfileVersion) -> dict[str, Any]:
    """The assembled profile with only this version's chosen facts, plus its headline."""
    chosen = set(version.fact_ids or [])
    facts = [f for f in repository.facts_for(db, account_id, statuses=("approved",))
             if f.kind not in CHOSEN_KINDS or f.id in chosen]
    prefs = repository.get_preferences(db, account_id)
    doc = repository.assemble(facts, prefs)
    doc["version"] = {"id": version.id, "name": version.name, "headline": version.headline,
                      "target_role": version.target_role}
    return doc


@router.get("", response_model=list[VersionOut])
def list_versions(account: Account = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(ProfileVersion).filter(ProfileVersion.account_id == account.id).order_by(ProfileVersion.id).all()
    return [_out(v) for v in rows]


@router.post("", response_model=VersionOut, status_code=201)
def create_version(payload: VersionIn, account: Account = Depends(get_current_user), db: Session = Depends(get_db)):
    if db.query(ProfileVersion).filter(ProfileVersion.account_id == account.id).count() >= MAX_VERSIONS:
        raise HTTPException(status_code=422, detail=f"You can keep up to {MAX_VERSIONS} versions.")
    v = ProfileVersion(account_id=account.id, name=payload.name.strip(), headline=payload.headline,
                       target_role=payload.target_role, fact_ids=_valid_ids(db, account.id, payload.fact_ids))
    db.add(v)
    db.commit()
    return _out(v)


@router.put("/{version_id}", response_model=VersionOut)
def update_version(version_id: int, payload: VersionIn, account: Account = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    v = _owned(db, account.id, version_id)
    v.name, v.headline, v.target_role = payload.name.strip(), payload.headline, payload.target_role
    v.fact_ids = _valid_ids(db, account.id, payload.fact_ids)
    db.commit()
    return _out(v)


@router.delete("/{version_id}", status_code=204)
def delete_version(version_id: int, account: Account = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(_owned(db, account.id, version_id))
    db.commit()
    return Response(status_code=204)


@router.get("/{version_id}/document")
def get_version_document(version_id: int, account: Account = Depends(get_current_user), db: Session = Depends(get_db)):
    return version_document(db, account.id, _owned(db, account.id, version_id))
