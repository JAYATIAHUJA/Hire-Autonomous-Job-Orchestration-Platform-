"""Online presence: the GitHub account (with an optional personal access token), LinkedIn,
website, portfolio and other profiles the user gives us directly, instead of OAuth.

Links are stored as approved ``link`` facts (source ``user_confirmed``), so they land in
the assembled profile document next to everything from the resume. The GitHub token is
a credential, not a fact: it is verified against GitHub, encrypted with the same Fernet
key as OAuth tokens, and kept on the account's GitHub identity, which is what the PoW
runner already reads (``github_tokens``). It is never returned.
"""

import datetime
import re
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession

from ..config import settings
from ..db import get_db
from ..facts import repository as facts_repo
from ..facts.models import ProfileFact
from ..profiles.pow_schemas import GITHUB_LOGIN_PATTERN
from .accounts import link_pow_profiles
from .consents import has_consent
from .crypto import EncryptionNotConfigured, encrypt_token, ensure_encryption_key
from .deps import get_current_user
from .models import Account, AuthIdentity

router = APIRouter(prefix="/v1/me/online-presence", tags=["me"])

# Marks the link facts this endpoint owns, so a save replaces exactly these and never
# touches links that came from a resume.
SOURCE_REF = "online_presence"
MAX_OTHERS = 10


class OtherLink(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    url: str = Field(min_length=1, max_length=300)


class PresenceIn(BaseModel):
    github_username: Optional[str] = Field(default=None, max_length=39)
    # Write-only. Omitted or empty keeps the saved token; ``clear_github_token`` removes it.
    github_token: Optional[str] = Field(default=None, max_length=255)
    clear_github_token: bool = False
    linkedin: Optional[str] = Field(default=None, max_length=300)
    website: Optional[str] = Field(default=None, max_length=300)
    portfolio: Optional[str] = Field(default=None, max_length=300)
    others: list[OtherLink] = Field(default_factory=list, max_length=MAX_OTHERS)


class PresenceOut(BaseModel):
    github_username: Optional[str] = None
    # A verified token is saved for this login (its value is never sent back).
    github_token_saved: bool = False
    linkedin: Optional[str] = None
    website: Optional[str] = None
    portfolio: Optional[str] = None
    others: list[OtherLink] = []
    # Nothing saved yet: these values were found in the approved resume facts, for the
    # user to check and save.
    from_resume: bool = False


PORTFOLIO_HOSTS = ("behance.net", "dribbble.com", "notion.site", "framer.website", "carrd.co", "webflow.io")


def _norm_url(url: str) -> str:
    p = urlparse(url if "://" in url else "https://" + url)
    host = (p.hostname or "").lower().removeprefix("www.")
    return f"{host}{p.path.rstrip('/')}".lower()


URL_IN_TEXT = re.compile(r"((?:https?://)?(?:www\.)?[a-z0-9.-]+\.[a-z]{2,}(?:/[^\s]*)?)", re.I)


def find_url(raw: Optional[str]) -> Optional[str]:
    """The first web address in a fact's url or sentence, without trailing punctuation."""
    match = URL_IN_TEXT.search(raw or "")
    if not match:
        return None
    url = match.group(1).rstrip(".,;:)]}'\"")
    return url if "://" in url else "https://" + url


def suggest_from_resume(db: DbSession, account_id: int) -> PresenceOut:
    """Sort the links found in approved resume facts into the presence fields."""
    out = PresenceOut(from_resume=True)
    links = (
        db.query(ProfileFact)
        .filter(ProfileFact.account_id == account_id, ProfileFact.kind == "link", ProfileFact.status == "approved")
        .order_by(ProfileFact.created_at)
        .all()
    )
    for fact in links:
        url = find_url((fact.structured or {}).get("url")) or find_url(fact.text)
        if not url:
            continue
        host = (urlparse(url).hostname or "").lower().removeprefix("www.")
        path = urlparse(url).path.strip("/")
        if host == "github.com" and path and re.fullmatch(GITHUB_LOGIN_PATTERN, path.split("/")[0]):
            out.github_username = out.github_username or path.split("/")[0]
        elif host.endswith("linkedin.com"):
            out.linkedin = out.linkedin or url
        elif any(host.endswith(h) for h in PORTFOLIO_HOSTS) and not out.portfolio:
            out.portfolio = url
        elif not out.website and not path:
            out.website = url
        elif len(out.others) < MAX_OTHERS:
            out.others.append(OtherLink(label=host.split(".")[0].capitalize() or "Link", url=url))
    return out


# --- GitHub checks (module-level so tests can swap them) --------------------------------

async def github_account_for_token(token: str) -> tuple[str, int]:
    """(login, numeric id) of the account the token belongs to. Raises ValueError if GitHub rejects it."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{settings.github_api_base}/user",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        )
    if resp.status_code == 401:
        raise ValueError("GitHub rejected this token. Check that you copied all of it and that it has not expired.")
    if resp.status_code != 200:
        raise ValueError(f"Could not check the token with GitHub (HTTP {resp.status_code}). Try again in a minute.")
    body = resp.json()
    return body["login"], int(body["id"])


async def github_user_exists(username: str) -> Optional[bool]:
    """True/False when GitHub answers clearly; None when it cannot be checked (rate limit, network)."""
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_app_token:
        headers["Authorization"] = f"Bearer {settings.github_app_token}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{settings.github_api_base}/users/{username}", headers=headers)
    except httpx.HTTPError:
        return None
    if resp.status_code == 404:
        return False
    return True if resp.status_code == 200 else None


# --- URL cleaning -----------------------------------------------------------------------

def clean_url(raw: Optional[str], field: str) -> Optional[str]:
    """Trim, add https:// when missing, and insist on a real http(s) host."""
    value = (raw or "").strip()
    if not value:
        return None
    if not re.match(r"^[a-z][a-z0-9+.-]*://", value, re.I):
        value = "https://" + value
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or "." not in (parsed.hostname or ""):
        raise HTTPException(status_code=422, detail=f"{field} must be a web address, like https://example.com.")
    return value


def clean_linkedin(raw: Optional[str]) -> Optional[str]:
    """A LinkedIn URL, or a bare profile handle turned into one."""
    value = (raw or "").strip().rstrip("/")
    if not value:
        return None
    if re.fullmatch(r"[A-Za-z0-9-]{3,100}", value):
        return f"https://www.linkedin.com/in/{value}"
    url = clean_url(value, "LinkedIn")
    host = (urlparse(url).hostname or "").lower()
    if not (host == "linkedin.com" or host.endswith(".linkedin.com")):
        raise HTTPException(status_code=422, detail="LinkedIn must be a linkedin.com profile address.")
    return url


# --- Storage ----------------------------------------------------------------------------

def _github_identity(db: DbSession, account_id: int) -> Optional[AuthIdentity]:
    return (
        db.query(AuthIdentity)
        .filter(AuthIdentity.account_id == account_id, AuthIdentity.provider == "github")
        .order_by(AuthIdentity.last_login_at.desc())
        .first()
    )


def _presence_facts(db: DbSession, account_id: int) -> list[ProfileFact]:
    return (
        db.query(ProfileFact)
        .filter(ProfileFact.account_id == account_id, ProfileFact.kind == "link", ProfileFact.source_ref == SOURCE_REF)
        .order_by(ProfileFact.created_at, ProfileFact.id)
        .all()
    )


def saved_github_username(db: DbSession, account_id: int) -> Optional[str]:
    """The GitHub login the user typed in, for PoW runs when no token is linked."""
    for fact in _presence_facts(db, account_id):
        if (fact.structured or {}).get("network") == "github":
            return (fact.structured or {}).get("username")
    return None


def read_presence(db: DbSession, account: Account) -> PresenceOut:
    facts = _presence_facts(db, account.id)
    out = PresenceOut() if facts else suggest_from_resume(db, account.id)
    for fact in facts:
        s = fact.structured or {}
        network = s.get("network")
        if network == "github":
            out.github_username = s.get("username")
        elif network in ("linkedin", "website", "portfolio"):
            setattr(out, network, s.get("url"))
        else:
            out.others.append(OtherLink(label=s.get("label") or "Link", url=s.get("url") or ""))
    identity = _github_identity(db, account.id)
    if identity is not None and identity.access_token_encrypted:
        out.github_token_saved = True
        out.github_username = out.github_username or identity.username
    return out


def _link(account_id: int, network: str, url: str, text: str, **extra: str) -> ProfileFact:
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    return ProfileFact(
        account_id=account_id,
        kind="link",
        text=text,
        structured={"url": url, "network": network, **extra},
        source="user_confirmed",
        source_ref=SOURCE_REF,
        inferred=False,
        status="approved",
        confirmed_at=now,
    )


# --- Routes -----------------------------------------------------------------------------

@router.get("", response_model=PresenceOut)
def get_presence(account: Account = Depends(get_current_user), db: DbSession = Depends(get_db)):
    return read_presence(db, account)


@router.put("", response_model=PresenceOut)
async def put_presence(payload: PresenceIn, account: Account = Depends(get_current_user),
                       db: DbSession = Depends(get_db)):
    username = (payload.github_username or "").strip().lstrip("@") or None
    if username and not re.fullmatch(GITHUB_LOGIN_PATTERN, username):
        raise HTTPException(status_code=422, detail="That is not a valid GitHub username.")
    token = (payload.github_token or "").strip() or None

    linkedin = clean_linkedin(payload.linkedin)
    website = clean_url(payload.website, "Website")
    portfolio = clean_url(payload.portfolio, "Portfolio")
    others = [(o.label.strip(), clean_url(o.url, o.label.strip() or "Link")) for o in payload.others if o.url.strip()]

    identity = _github_identity(db, account.id)

    if token:
        # The token exists only to read GitHub for the proof-of-work analysis.
        if not has_consent(account, "github"):
            raise HTTPException(
                status_code=403,
                detail="Turn on “Analyse my GitHub” in your privacy settings before saving a GitHub token.",
            )
        try:
            ensure_encryption_key()
        except EncryptionNotConfigured as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        try:
            login, github_id = await github_account_for_token(token)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        if username and login.lower() != username.lower():
            raise HTTPException(status_code=422, detail=f"This token belongs to @{login}, not @{username}.")
        username = login
        taken = (
            db.query(AuthIdentity)
            .filter(AuthIdentity.provider == "github", AuthIdentity.subject == str(github_id),
                    AuthIdentity.account_id != account.id)
            .first()
        )
        if taken:
            raise HTTPException(status_code=409, detail=f"@{login} is already connected to another Hire account.")
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        if identity is None:
            identity = AuthIdentity(account_id=account.id, provider="github", subject=str(github_id))
            db.add(identity)
        identity.subject = str(github_id)
        identity.username = login
        identity.access_token_encrypted = encrypt_token(token)
        identity.last_login_at = now
        link_pow_profiles(db, account, login)
    elif identity is not None and (
        payload.clear_github_token or not username or (identity.username or "").lower() != username.lower()
    ):
        # The saved token is for another login (or the user removed it). An OAuth identity
        # that is their only way in stays, minus the token.
        only_way_in = len(account.identities) == 1
        if only_way_in:
            identity.access_token_encrypted = None
        else:
            db.delete(identity)
    elif username and username.lower() != (saved_github_username(db, account.id) or "").lower():
        if await github_user_exists(username) is False:
            raise HTTPException(status_code=422, detail=f"There is no GitHub account called @{username}.")

    for fact in _presence_facts(db, account.id):
        db.delete(fact)
    db.flush()
    facts: list[ProfileFact] = []
    if username:
        facts.append(_link(account.id, "github", f"https://github.com/{username}", f"GitHub: github.com/{username}",
                           username=username))
    if linkedin:
        facts.append(_link(account.id, "linkedin", linkedin, f"LinkedIn: {linkedin}"))
    if website:
        facts.append(_link(account.id, "website", website, f"Website: {website}"))
    if portfolio:
        facts.append(_link(account.id, "portfolio", portfolio, f"Portfolio: {portfolio}"))
    for label, url in others:
        facts.append(_link(account.id, "other", url, f"{label}: {url}", label=label))
    db.add_all(facts)
    # The same link found in the resume would now be listed twice: retire that copy.
    saved = {_norm_url(f.structured["url"]) for f in facts}
    for old in (
        db.query(ProfileFact)
        .filter(ProfileFact.account_id == account.id, ProfileFact.kind == "link", ProfileFact.status == "approved",
                ProfileFact.source_ref.is_distinct_from(SOURCE_REF))
        .all()
    ):
        url = find_url((old.structured or {}).get("url")) or find_url(old.text)
        if url and _norm_url(url) in saved:
            old.status = "rejected"
    db.flush()
    facts_repo.refresh_profile(db, account.id)
    db.commit()
    db.refresh(account)
    return read_presence(db, account)
