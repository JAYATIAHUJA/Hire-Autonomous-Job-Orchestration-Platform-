"""Login, logout and "who am I": /v1/auth/* and /v1/me.

The public endpoints here are the only ones (with /health) that work without a
session. State-changing ones still require ``X-Requested-With`` so a cross-site
form can't log a victim into an attacker's account.
"""

import secrets
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session as DbSession

from ..config import settings
from ..db import get_db
from . import oauth, otp
from .accounts import AccountUnavailable, IdentityConflict, link_pow_profiles, normalize_email, sign_in_with_identity
from .crypto import EncryptionNotConfigured, encrypt_token, ensure_encryption_key
from .deps import get_current_user, get_optional_user, require_csrf_header
from .models import Account
from .schemas import EmailRequest, MeOut, OtpSendResponse, OtpVerifyRequest
from .sessions import clear_session_cookie, create_session, revoke_session, set_session_cookie

router = APIRouter(prefix="/v1", tags=["auth"])

OAUTH_PROVIDERS = ("github", "google")
STATE_COOKIE = "hire_oauth_state"
STATE_MAX_AGE = 600


def to_me(account: Account) -> MeOut:
    return MeOut(
        id=account.id,
        email=account.email,
        display_name=account.display_name,
        role=account.role,
        created_at=account.created_at,
        providers=sorted({i.provider for i in account.identities}),
    )


def _start_session(db: DbSession, request: Request, response: Response, account: Account) -> None:
    # A fresh token on every login; the one the browser held before is retired.
    revoke_session(db, request.cookies.get(settings.session_cookie_name))
    db.commit()
    token = create_session(db, account, request.headers.get("user-agent"))
    set_session_cookie(response, token)


def _client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _require_email(raw: str) -> str:
    email = normalize_email(raw)
    if not email:
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    return email


@router.post("/auth/dev-login", response_model=MeOut, dependencies=[Depends(require_csrf_header)])
def dev_login(payload: EmailRequest, request: Request, response: Response, db: DbSession = Depends(get_db)):
    """Log in as any email without proof. Exists only when ENV=dev."""
    if settings.env != "dev":
        raise HTTPException(status_code=404, detail="Not Found")
    email = _require_email(payload.email)
    try:
        account, _ = sign_in_with_identity(db, provider="email", subject=email, email=email, email_verified=True)
    except AccountUnavailable as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    db.commit()
    _start_session(db, request, response, account)
    return to_me(account)


@router.post(
    "/auth/otp/send", response_model=OtpSendResponse, status_code=202, dependencies=[Depends(require_csrf_header)]
)
def otp_send(payload: EmailRequest, request: Request, db: DbSession = Depends(get_db)):
    """Email a login code. Answers the same whether or not the address has an account."""
    email = _require_email(payload.email)
    try:
        otp.send_code(db, email, _client_ip(request))
    except otp.RateLimited as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except Exception as exc:  # noqa: BLE001 - mail delivery failure
        raise HTTPException(status_code=502, detail=f"Could not send the code: {exc}")
    return OtpSendResponse(expires_in_seconds=int(otp.CODE_TTL.total_seconds()))


@router.post("/auth/otp/verify", response_model=MeOut, dependencies=[Depends(require_csrf_header)])
def otp_verify(payload: OtpVerifyRequest, request: Request, response: Response, db: DbSession = Depends(get_db)):
    email = _require_email(payload.email)
    try:
        otp.verify_code(db, email, payload.code)
    except otp.TooManyAttempts as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except otp.InvalidCode as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        account, _ = sign_in_with_identity(db, provider="email", subject=email, email=email, email_verified=True)
    except AccountUnavailable as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    db.commit()
    _start_session(db, request, response, account)
    return to_me(account)


def _check_provider(provider: str) -> None:
    if provider not in OAUTH_PROVIDERS:
        raise HTTPException(status_code=404, detail="Not Found")


@router.get("/auth/{provider}/start")
def oauth_start(provider: str):
    """Redirect the browser to GitHub or Google. A random ``state`` ties the callback to this browser."""
    _check_provider(provider)
    try:
        if provider == "github":
            ensure_encryption_key()  # fail here, not after the user has approved on GitHub
        state = secrets.token_urlsafe(24)
        url = oauth.authorize_url(provider, state)
    except (oauth.OAuthNotConfigured, EncryptionNotConfigured) as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    response = RedirectResponse(url, status_code=302)
    response.set_cookie(
        STATE_COOKIE,
        f"{provider}.{state}",
        max_age=STATE_MAX_AGE,
        path="/v1/auth",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )
    return response


def _web_redirect(path: str = "/", **params: str) -> RedirectResponse:
    url = settings.web_app_url.rstrip("/") + path
    if params:
        url += "?" + urlencode(params)
    response = RedirectResponse(url, status_code=302)
    response.delete_cookie(STATE_COOKIE, path="/v1/auth")
    return response


@router.get("/auth/{provider}/callback")
async def oauth_callback(
    provider: str,
    request: Request,
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    db: DbSession = Depends(get_db),
    current: Optional[Account] = Depends(get_optional_user),
):
    """Finish an OAuth login. If someone is already logged in, the identity is linked to them."""
    _check_provider(provider)
    expected = request.cookies.get(STATE_COOKIE) or ""
    if not state or not secrets.compare_digest(expected, f"{provider}.{state}"):
        return _web_redirect("/login", error="state_mismatch")
    if error or not code:
        return _web_redirect("/login", error="denied")

    try:
        user = await (oauth.github_user(code) if provider == "github" else oauth.google_user(code))
    except (oauth.OAuthError, oauth.OAuthNotConfigured):
        return _web_redirect("/login", error="provider_error")

    try:
        account, identity = sign_in_with_identity(
            db,
            provider=user.provider,
            subject=user.subject,
            email=user.email,
            email_verified=user.email_verified,
            display_name=user.display_name,
            username=user.username,
            current=current,
        )
        if provider == "github":
            if user.access_token:
                identity.access_token_encrypted = encrypt_token(user.access_token)
            link_pow_profiles(db, account, user.username or "")
        db.commit()
    except IdentityConflict:
        db.rollback()
        return _web_redirect("/login", error="identity_in_use")
    except AccountUnavailable:
        db.rollback()
        return _web_redirect("/login", error="account_deleted")
    except EncryptionNotConfigured:
        db.rollback()
        return _web_redirect("/login", error="server_misconfigured")

    response = _web_redirect("/")
    _start_session(db, request, response, account)
    return response


@router.post("/auth/logout", status_code=204, dependencies=[Depends(require_csrf_header)])
def logout(request: Request, db: DbSession = Depends(get_db)):
    revoke_session(db, request.cookies.get(settings.session_cookie_name))
    response = Response(status_code=204)
    clear_session_cookie(response)
    return response


@router.get("/me", response_model=MeOut)
def me(account: Account = Depends(get_current_user)):
    return to_me(account)
