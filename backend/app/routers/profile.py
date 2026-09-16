import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from .. import models
from ..db import get_db
from ..github_client import GitHubAPIError
from ..schemas import AnalyzeRequest, AnalyzeResponse, ProfileOut
from ..services.confidence_service import compute_confidence
from ..services.fetch_service import fetch_user_data
from ..services.metrics_service import compute_aggregate_metrics
from ..services.skill_service import infer_skills

router = APIRouter(prefix="/api/profile", tags=["profile"])

TIER_ORDER = {"Strong": 0, "Moderate": 1, "Limited": 2}


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze_profile(payload: AnalyzeRequest, db: Session = Depends(get_db)):
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=422, detail="Username is required.")

    try:
        data = fetch_user_data(username, payload.token)
    except GitHubAPIError as e:
        if e.rate_limited:
            raise HTTPException(status_code=429, detail=str(e))
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail=f"GitHub user '{username}' not found.")
        if e.status_code == 401:
            raise HTTPException(status_code=401, detail="Invalid GitHub token.")
        raise HTTPException(status_code=502, detail=str(e))

    repo_data = data["repos"]
    if not repo_data:
        raise HTTPException(status_code=404, detail="No non-fork repositories found for this user.")

    aggregate = compute_aggregate_metrics(repo_data)
    skills = infer_skills(repo_data)

    user = models.User(username=username, timeline_json=json.dumps(aggregate["timeline"]))
    db.add(user)

    for repo in repo_data:
        user.repos.append(
            models.Repo(
                full_name=repo["full_name"],
                url=repo["url"],
                primary_language=repo["primary_language"],
                commit_count=repo["commit_count"],
                additions=repo["additions"],
                deletions=repo["deletions"],
                pr_count=repo["pr_count"],
                first_contribution=_parse_dt(repo["first_contribution"]),
                last_contribution=_parse_dt(repo["last_contribution"]),
            )
        )

    for name, s in skills.items():
        user.skills.append(
            models.Skill(
                name=name,
                confidence_tier=compute_confidence(s["commit_count"], len(s["repos"]), s["last_active"]),
                commit_count=s["commit_count"],
                repo_count=len(s["repos"]),
                pr_count=s["pr_count"],
                first_active=_parse_dt(s["first_active"]),
                last_active=_parse_dt(s["last_active"]),
                evidence=[models.SkillEvidence(**ev) for ev in s["repos"].values()],
            )
        )

    db.commit()
    return AnalyzeResponse(profile_id=user.id, username=user.username)


@router.get("/{profile_id}", response_model=ProfileOut)
def get_profile(profile_id: int, db: Session = Depends(get_db)):
    user = (
        db.query(models.User)
        .options(selectinload(models.User.repos), selectinload(models.User.skills).selectinload(models.Skill.evidence))
        .filter(models.User.id == profile_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="Profile not found.")

    skills = sorted(user.skills, key=lambda s: (TIER_ORDER.get(s.confidence_tier, 3), -s.commit_count))
    repos = sorted(user.repos, key=lambda r: -r.commit_count)

    return ProfileOut(
        profile_id=user.id,
        username=user.username,
        total_repos=len(repos),
        total_commits=sum(r.commit_count for r in repos),
        total_additions=sum(r.additions for r in repos),
        total_deletions=sum(r.deletions for r in repos),
        languages=sorted({r.primary_language for r in repos if r.primary_language}),
        timeline=json.loads(user.timeline_json or "[]"),
        repos=repos,
        skills=skills,
    )
