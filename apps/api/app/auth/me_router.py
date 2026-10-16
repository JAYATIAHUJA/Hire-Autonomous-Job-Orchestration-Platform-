"""The logged-in account's own settings: /v1/me consent, onboarding and preferences.

GET /v1/me lives in ``router.py`` with login; this module holds what the web
onboarding flow (WP5) writes back.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session as DbSession

from ..config import settings
from ..db import get_db
from ..facts import repository as facts_repository
from ..facts.storage import ObjectStore, get_object_store
from .deps import get_current_user
from .erasure import erase_account
from .sessions import clear_session_cookie
from .models import Account, PrivacyConsent, utcnow
from .router import consent_out, to_me
from .schemas import ConsentOut, ConsentRequest, MeOut, MePatch, Preferences

logger = logging.getLogger("hire.auth")

router = APIRouter(prefix="/v1/me", tags=["me"])


@router.post("/consents", response_model=ConsentOut, status_code=201)
def record_consent(payload: ConsentRequest, request: Request, account: Account = Depends(get_current_user),
                   db: DbSession = Depends(get_db)):
    """Record acceptance of the privacy notice. Append-only: a change of mind is a new row."""
    if payload.notice_version != settings.privacy_notice_version:
        raise HTTPException(
            status_code=422,
            detail=f"Notice {payload.notice_version} is not the current notice ({settings.privacy_notice_version}). "
                   "Reload the page and review the notice again.",
        )
    row = PrivacyConsent(
        account_id=account.id,
        notice_version=payload.notice_version,
        notice_hash=payload.notice_hash,
        purposes=payload.purposes.model_dump(),
        accepted_at=utcnow(),
        user_agent=(request.headers.get("user-agent") or "")[:300] or None,
    )
    db.add(row)
    db.commit()
    db.refresh(account)
    return consent_out(row)


@router.patch("", response_model=MeOut)
def update_me(payload: MePatch, account: Account = Depends(get_current_user), db: DbSession = Depends(get_db)):
    if payload.display_name is not None:
        account.display_name = payload.display_name.strip() or None
    if payload.onboarding_completed:
        if account.onboarding_completed_at is None:
            account.onboarding_completed_at = utcnow()
    elif payload.onboarding_completed is False:
        raise HTTPException(status_code=422, detail="Onboarding cannot be un-completed.")
    db.commit()
    db.refresh(account)
    return to_me(account)


@router.delete("", status_code=204)
def delete_me(account: Account = Depends(get_current_user), db: DbSession = Depends(get_db),
              store: Optional[ObjectStore] = Depends(get_object_store)):
    """DPDP erasure of the whole account: every personal row and stored file, then the login."""
    try:
        erase_account(db, account, store)
    except Exception as exc:
        db.rollback()
        logger.error("account erasure failed for account_id=%s: %s", account.id, exc)
        raise HTTPException(status_code=503, detail="Erasure could not finish. Please retry.") from exc
    response = Response(status_code=204)
    clear_session_cookie(response)
    return response


@router.get("/preferences", response_model=Preferences)
def get_preferences(account: Account = Depends(get_current_user), db: DbSession = Depends(get_db)):
    return Preferences(**facts_repository.get_preferences(db, account.id))


@router.patch("/preferences", response_model=Preferences)
def update_preferences(payload: Preferences, account: Account = Depends(get_current_user),
                       db: DbSession = Depends(get_db)):
    """Job preferences (roles, locations, remote, experience, salary floor, deal-breakers).
    Stored with the candidate profile so the matcher reads one document."""
    current = facts_repository.get_preferences(db, account.id)
    merged = {**current, **payload.model_dump(exclude_unset=True)}
    saved = facts_repository.set_preferences(db, account.id, Preferences(**merged).model_dump())
    db.commit()
    return Preferences(**saved)
