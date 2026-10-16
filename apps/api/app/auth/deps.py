"""FastAPI dependencies every owner-scoped route uses.

    @router.get("/thing")
    def read_thing(account: Account = Depends(get_current_user)): ...

``get_current_user`` reads the session cookie and returns the logged-in ``Account``,
or answers 401. On state-changing requests it also enforces the CSRF rule: the
request must carry an ``X-Requested-With`` header, which a cross-site form or a
simple cross-origin fetch cannot set.
"""

from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session as DbSession

from ..config import settings
from ..db import get_db
from .models import Account
from .sessions import resolve_session

CSRF_HEADER = "X-Requested-With"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def require_csrf_header(request: Request) -> None:
    """403 unless a state-changing request carries ``X-Requested-With`` (any non-empty value)."""
    if request.method.upper() in SAFE_METHODS:
        return
    if not (request.headers.get(CSRF_HEADER) or "").strip():
        raise HTTPException(status_code=403, detail=f"Missing {CSRF_HEADER} header.")


def get_optional_user(request: Request, db: DbSession = Depends(get_db)) -> Optional[Account]:
    """The logged-in account, or None. Does not enforce CSRF; use only on safe requests."""
    return resolve_session(db, request.cookies.get(settings.session_cookie_name))


def get_current_user(request: Request, db: DbSession = Depends(get_db)) -> Account:
    account = resolve_session(db, request.cookies.get(settings.session_cookie_name))
    if account is None:
        raise HTTPException(status_code=401, detail="Not logged in.")
    require_csrf_header(request)
    request.state.account = account
    return account


def require_admin(account: Account = Depends(get_current_user)) -> Account:
    if account.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only.")
    return account
