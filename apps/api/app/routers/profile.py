"""HTTP endpoints for building and reading proof-of-work profiles.

Thin adapter: validate the request, delegate to the analysis + profile layers,
and map failures to HTTP responses. All real work lives in ``services`` and ``profiles``.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.consents import require_github_consent
from ..auth.deps import get_current_user
from ..auth.models import Account
from ..db import get_db
from ..github_client import GitHubAPIError
from ..profiles import builder, repository, serializer
from ..profiles.errors import http_error_for
from ..schemas import AnalyzeRequest, AnalyzeResponse, ProfileOut
from ..services.fetch_service import fetch_contributions

router = APIRouter(prefix="/api/profile", tags=["profile"], dependencies=[Depends(get_current_user)])


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_profile(
    payload: AnalyzeRequest, db: Session = Depends(get_db), account: Account = Depends(require_github_consent)
):
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=422, detail="Username is required.")
    token = (payload.token or "").strip() or None

    try:
        data = await fetch_contributions(username, token)
    except GitHubAPIError as e:
        raise http_error_for(e, username)

    if not data["projects"]:
        raise HTTPException(status_code=404, detail="No non-fork repositories or merged pull requests found.")

    profile = builder.build_profile(username, data)
    profile.account_id = account.id
    user = repository.save(db, profile)
    return AnalyzeResponse(profile_id=user.id, username=user.username)


@router.get("/{profile_id}", response_model=ProfileOut)
def get_profile(profile_id: int, db: Session = Depends(get_db), account: Account = Depends(get_current_user)):
    user = repository.load(db, profile_id, account.id)
    if not user:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return serializer.serialize_profile(user)
