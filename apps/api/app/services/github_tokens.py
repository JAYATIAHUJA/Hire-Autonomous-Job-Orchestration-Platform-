"""Which GitHub token a background PoW run uses.

The user's own OAuth token is preferred: it carries their 5,000/hour budget and
lets GraphQL return their contribution totals. WP1 stores that token encrypted;
until it lands nothing is registered and every run falls back to the app token.

WP1 wires its lookup in once at start-up::

    from app.services.github_tokens import set_user_token_provider
    set_user_token_provider(lambda db, account_id: decrypt_github_token(db, account_id))
"""

from typing import Callable, Optional

from sqlalchemy.orm import Session

from ..config import settings

UserTokenProvider = Callable[[Session, int], Optional[str]]

_user_token_provider: Optional[UserTokenProvider] = None


def set_user_token_provider(provider: Optional[UserTokenProvider]) -> None:
    global _user_token_provider
    _user_token_provider = provider


LinkedLoginProvider = Callable[[Session, int], Optional[str]]

_linked_login_provider: Optional[LinkedLoginProvider] = None


def set_linked_login_provider(provider: Optional[LinkedLoginProvider]) -> None:
    """WP1: register "which GitHub login has this account linked?" (None if not linked)."""
    global _linked_login_provider
    _linked_login_provider = provider


def linked_login(db: Session, account_id: int) -> Optional[str]:
    return _linked_login_provider(db, account_id) if _linked_login_provider else None


def resolve_token(db: Session, account_id: int) -> tuple[Optional[str], str]:
    """(token, source) where source is "user", "app" or "none" (recorded on the run)."""
    if _user_token_provider is not None:
        if token := _user_token_provider(db, account_id):
            return token, "user"
    if settings.github_app_token:
        return settings.github_app_token, "app"
    return None, "none"
