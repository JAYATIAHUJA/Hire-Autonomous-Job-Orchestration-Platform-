"""Signed consent receipts for outbound applications.

A swipe right is the affirmative action: it is the only thing that authorises the
platform to send a candidate's data to an employer. Each one writes a tamper
evident receipt carrying *who* consented, *when*, *why* (the purpose) and the
*named employer* the data goes to, signed with HMAC-SHA256 over a canonical JSON
encoding so the log can be replayed and verified later.
"""

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from ..config import settings

CONSENT_VERSION = "1.0"
CONSENT_ALGORITHM = "HMAC-SHA256"
DEFAULT_PURPOSE = "Submit this candidate's profile and tailored resume to the named employer for this role."


def new_consent_id() -> str:
    return f"csnt_{uuid.uuid4().hex[:16]}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_consent_payload(
    *,
    consent_id: str,
    subject: str,
    employer_name: str,
    job_id: str,
    role_title: str,
    purpose: str = DEFAULT_PURPOSE,
    granted_at: Optional[str] = None,
) -> dict[str, Any]:
    """Assemble the exact record that gets signed and stored."""
    return {
        "version": CONSENT_VERSION,
        "consent_id": consent_id,
        "action": "swipe_right",
        "subject": subject,
        "employer_name": employer_name,
        "job_id": job_id,
        "role_title": role_title,
        "purpose": purpose,
        "granted_at": granted_at or utc_now_iso(),
    }


def canonical_json(payload: dict[str, Any]) -> str:
    """Deterministic encoding — key order and spacing must not affect the signature."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _secret(secret: Optional[str]) -> bytes:
    return (secret or settings.consent_signing_secret).encode("utf-8")


def sign_payload(payload: dict[str, Any], secret: Optional[str] = None) -> str:
    """HMAC-SHA256 hex digest of the canonical encoding."""
    return hmac.new(_secret(secret), canonical_json(payload).encode("utf-8"), hashlib.sha256).hexdigest()


def verify_payload(payload: dict[str, Any], signature: str, secret: Optional[str] = None) -> bool:
    """Constant-time check that a stored receipt still matches its signature."""
    if not signature:
        return False
    return hmac.compare_digest(sign_payload(payload, secret), signature)


def issue_consent(
    *,
    subject: str,
    employer_name: str,
    job_id: str,
    role_title: str,
    purpose: str = DEFAULT_PURPOSE,
    secret: Optional[str] = None,
) -> tuple[dict[str, Any], str]:
    """Mint a fresh consent receipt and its signature."""
    payload = build_consent_payload(
        consent_id=new_consent_id(),
        subject=subject,
        employer_name=employer_name,
        job_id=job_id,
        role_title=role_title,
        purpose=purpose,
    )
    return payload, sign_payload(payload, secret)
