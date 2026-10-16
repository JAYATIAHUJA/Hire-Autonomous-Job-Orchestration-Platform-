"""DPDP consent: what the account agreed to, and the gates that enforce it.

The privacy notice is shown before any data is collected; the web client records
the notice version, the sha256 of its exact text and one switch per purpose. The
API then refuses to collect for a purpose the account has not switched on, so the
consent screen is not only a UI promise.
"""

from typing import Callable, Optional

from fastapi import Depends, HTTPException

from ..config import settings
from .deps import get_current_user
from .models import Account, PrivacyConsent

PURPOSES = ("github", "resume", "email")
PURPOSE_LABELS = {"github": "analyse your GitHub", "resume": "parse your resume", "email": "read your job email"}


def current_consent(account: Account) -> Optional[PrivacyConsent]:
    """The newest consent, if it was given to the notice version now in force."""
    consent = account.current_consent
    if consent is None or consent.notice_version != settings.privacy_notice_version:
        return None
    return consent


def has_consent(account: Account, purpose: str) -> bool:
    consent = current_consent(account)
    return bool(consent and (consent.purposes or {}).get(purpose))


def require_consent(purpose: str) -> Callable[[Account], Account]:
    if purpose not in PURPOSES:
        raise ValueError(f"unknown consent purpose: {purpose}")

    def dependency(account: Account = Depends(get_current_user)) -> Account:
        if not has_consent(account, purpose):
            raise HTTPException(
                status_code=403,
                detail=f"You have not agreed to let Hire {PURPOSE_LABELS[purpose]}. Turn it on in your privacy settings.",
            )
        return account

    dependency.__name__ = f"require_{purpose}_consent"
    return dependency


# Module-level so routes and test overrides share the same dependency objects.
require_github_consent = require_consent("github")
require_resume_consent = require_consent("resume")
