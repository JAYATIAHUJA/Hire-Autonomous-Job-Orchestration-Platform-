"""Email one-time codes: 6 digits, 10 minutes, 5 tries, rate limited, stored hashed."""

import datetime
import hashlib
import hmac
import re
import secrets
from typing import Optional

from sqlalchemy.orm import Session as DbSession

from .mailer import OtpSender, get_sender
from .models import OtpCode, utcnow

CODE_TTL = datetime.timedelta(minutes=10)
MAX_ATTEMPTS = 5
MAX_SENDS_PER_EMAIL_PER_HOUR = 5
MAX_SENDS_PER_IP_PER_HOUR = 20
CODE_RE = re.compile(r"^\d{6}$")


class RateLimited(Exception):
    """Too many codes requested for this email or from this IP."""


class InvalidCode(Exception):
    """Wrong, expired, superseded or unknown code."""


class TooManyAttempts(Exception):
    """The code was guessed wrong too often; a new one must be requested."""


def hash_code(email: str, code: str) -> str:
    # Bound to the email so one leaked hash can't be replayed for another address.
    return hashlib.sha256(f"{email}:{code}".encode("utf-8")).hexdigest()


def send_code(db: DbSession, email: str, ip: Optional[str], sender: Optional[OtpSender] = None) -> None:
    now = utcnow()
    hour_ago = now - datetime.timedelta(hours=1)
    recent = db.query(OtpCode).filter(OtpCode.created_at > hour_ago)
    if recent.filter(OtpCode.email == email).count() >= MAX_SENDS_PER_EMAIL_PER_HOUR:
        raise RateLimited("Too many codes requested for this email. Try again later.")
    if ip and recent.filter(OtpCode.ip == ip).count() >= MAX_SENDS_PER_IP_PER_HOUR:
        raise RateLimited("Too many codes requested from this network. Try again later.")

    # Only the newest code works: requesting another one retires the old ones.
    db.query(OtpCode).filter(OtpCode.email == email, OtpCode.consumed_at.is_(None)).update(
        {OtpCode.consumed_at: now}, synchronize_session=False
    )
    code = f"{secrets.randbelow(10**6):06d}"
    db.add(OtpCode(email=email, code_hash=hash_code(email, code), ip=ip, created_at=now, expires_at=now + CODE_TTL))
    db.commit()

    (sender or get_sender()).send(email, code)


def verify_code(db: DbSession, email: str, code: str) -> None:
    """Consume the code or raise. Each wrong guess burns one of the code's tries."""
    code = (code or "").strip()
    row = (
        db.query(OtpCode)
        .filter(OtpCode.email == email, OtpCode.consumed_at.is_(None))
        .order_by(OtpCode.created_at.desc(), OtpCode.id.desc())
        .first()
    )
    now = utcnow()
    if row is None or row.expires_at <= now:
        raise InvalidCode("That code is invalid or has expired.")
    if row.attempts >= MAX_ATTEMPTS:
        raise TooManyAttempts("Too many wrong codes. Request a new one.")

    if not CODE_RE.match(code) or not hmac.compare_digest(row.code_hash, hash_code(email, code)):
        row.attempts += 1
        db.commit()
        raise InvalidCode("That code is invalid or has expired.")

    row.consumed_at = now
    db.commit()
