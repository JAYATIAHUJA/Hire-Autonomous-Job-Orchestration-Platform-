"""Finding or creating the account a login belongs to."""

import re
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session as DbSession

from .. import models as pow_models
from ..config import settings
from .models import Account, AuthIdentity, utcnow

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class IdentityConflict(ValueError):
    """The identity already belongs to a different account than the one logged in."""


class AccountUnavailable(ValueError):
    """The identity's account has been erased."""


def normalize_email(raw: Optional[str]) -> Optional[str]:
    email = (raw or "").strip().lower()
    return email if EMAIL_RE.match(email) else None


def _apply_admin_bootstrap(account: Account) -> None:
    admins = {e.strip().lower() for e in settings.admin_emails if e.strip()}
    if account.email and account.email in admins and account.role == "user":
        account.role = "admin"


def find_by_email(db: DbSession, email: str) -> Optional[Account]:
    return db.query(Account).filter(Account.email == email).first()


def sign_in_with_identity(
    db: DbSession,
    *,
    provider: str,
    subject: str,
    email: Optional[str] = None,
    email_verified: bool = False,
    display_name: Optional[str] = None,
    username: Optional[str] = None,
    current: Optional[Account] = None,
) -> tuple[Account, AuthIdentity]:
    """Resolve a provider login to an account, creating or linking as needed.

    Order: a known identity wins; else a logged-in account adopts it; else an
    account with the same *verified* email adopts it; else a new account is made.
    An unverified provider email never links to, or claims, an existing account.
    """
    email = normalize_email(email) if email_verified else None
    identity = (
        db.query(AuthIdentity)
        .filter(AuthIdentity.provider == provider, AuthIdentity.subject == subject)
        .first()
    )

    if identity:
        account = identity.account
        if current is not None and current.id != account.id:
            raise IdentityConflict(f"This {provider} login is already linked to another account.")
    elif current is not None:
        account = current
    else:
        account = find_by_email(db, email) if email else None
        if account is None:
            account = Account(email=email, display_name=display_name or username or email, role="user")
            db.add(account)
            db.flush()

    if account.deleted_at is not None:
        raise AccountUnavailable("This account has been deleted.")

    if identity is None:
        identity = AuthIdentity(account_id=account.id, provider=provider, subject=subject)
        db.add(identity)
    identity.username = username or identity.username
    identity.email = email or identity.email
    identity.last_login_at = utcnow()

    if account.email is None and email and find_by_email(db, email) is None:
        account.email = email
    if not account.display_name:
        account.display_name = display_name or username or email
    _apply_admin_bootstrap(account)

    db.flush()
    return account, identity


def link_pow_profiles(db: DbSession, account: Account, github_login: str) -> int:
    """Claim analysed GitHub profiles (``users`` rows) with this login that nobody owns yet."""
    if not github_login:
        return 0
    rows = (
        db.query(pow_models.User)
        .filter(func.lower(pow_models.User.username) == github_login.lower(), pow_models.User.account_id.is_(None))
        .all()
    )
    for row in rows:
        row.account_id = account.id
    return len(rows)
