"""Opaque session tokens: issued into an HttpOnly cookie, stored only as a sha256."""

import datetime
import hashlib
import secrets
from typing import Optional

from fastapi import Response
from sqlalchemy.orm import Session as DbSession

from ..config import settings
from .models import Account, Session, utcnow


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: DbSession, account: Account, user_agent: Optional[str] = None) -> str:
    """Start a session for ``account`` and return the raw token (shown once, never stored)."""
    token = secrets.token_urlsafe(32)
    now = utcnow()
    db.add(
        Session(
            account_id=account.id,
            token_hash=hash_token(token),
            created_at=now,
            expires_at=now + datetime.timedelta(days=settings.session_ttl_days),
            user_agent=(user_agent or "")[:400] or None,
        )
    )
    db.commit()
    return token


def resolve_session(db: DbSession, token: Optional[str]) -> Optional[Account]:
    """The live account behind a token, or None if it is unknown, revoked, expired or erased."""
    if not token:
        return None
    row = db.query(Session).filter(Session.token_hash == hash_token(token)).first()
    if not row or row.revoked_at is not None or row.expires_at <= utcnow():
        return None
    account = row.account
    if account is None or account.deleted_at is not None:
        return None
    return account


def revoke_session(db: DbSession, token: Optional[str]) -> None:
    if not token:
        return
    row = db.query(Session).filter(Session.token_hash == hash_token(token)).first()
    if row and row.revoked_at is None:
        row.revoked_at = utcnow()
        db.commit()


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_days * 24 * 3600,
        path="/",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )
