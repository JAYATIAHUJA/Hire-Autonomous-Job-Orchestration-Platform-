"""Read access to a user's stored OAuth tokens, for the GitHub analysis (WP2)."""

from typing import Optional

from sqlalchemy.orm import Session as DbSession

from .crypto import decrypt_token
from .models import AuthIdentity


def get_github_token(db: DbSession, account_id: int) -> Optional[str]:
    """The account's GitHub OAuth token, decrypted, or None if they never linked GitHub."""
    identity = (
        db.query(AuthIdentity)
        .filter(AuthIdentity.account_id == account_id, AuthIdentity.provider == "github")
        .order_by(AuthIdentity.last_login_at.desc())
        .first()
    )
    return decrypt_token(identity.access_token_encrypted) if identity else None
