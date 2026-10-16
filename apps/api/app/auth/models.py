"""Login accounts, the identities that sign into them, and their sessions.

An ``Account`` is a person who logs in. It is not ``app.models.User``, which is a
GitHub profile we analysed; that row points back here through ``users.account_id``.
Every personal row in the app is owned by an ``accounts.id`` (DPDP: erasable per person).

Datetimes are stored as naive UTC so SQLite and Postgres compare them the same way.
"""

import datetime

from sqlalchemy import JSON, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from ..db import Base

ROLES = ("user", "admin", "support")
PROVIDERS = ("github", "google", "email")


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (CheckConstraint("role IN ('user', 'admin', 'support')", name="ck_accounts_role"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Lower-cased. Nullable: a GitHub login without a verified email has none.
    email = Column(String, nullable=True, unique=True)
    display_name = Column(String, nullable=True)
    role = Column(String, nullable=False, default="user")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    deleted_at = Column(DateTime, nullable=True)
    # Set when the user finishes the first-run onboarding wizard (web route guard).
    onboarding_completed_at = Column(DateTime, nullable=True)

    identities = relationship("AuthIdentity", back_populates="account", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="account", cascade="all, delete-orphan")
    consents = relationship(
        "PrivacyConsent", back_populates="account", cascade="all, delete-orphan",
        order_by="(PrivacyConsent.accepted_at.desc(), PrivacyConsent.id.desc())",
    )

    @property
    def current_consent(self) -> "PrivacyConsent | None":
        return self.consents[0] if self.consents else None

    @property
    def ref(self) -> str:
        """The stable, non-personal name for this account in signed receipts and keys."""
        return f"account:{self.id}"


class AuthIdentity(Base):
    """One way into an account: a GitHub user id, a Google ``sub``, or an email address."""

    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "subject", name="uq_auth_identities_provider_subject"),
        CheckConstraint("provider IN ('github', 'google', 'email')", name="ck_auth_identities_provider"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    provider = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    # GitHub login, or the provider's email, for display and PoW linking only.
    username = Column(String, nullable=True)
    email = Column(String, nullable=True)
    # Fernet ciphertext of the provider's OAuth access token (GitHub only, today).
    access_token_encrypted = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    last_login_at = Column(DateTime, nullable=True)

    account = relationship("Account", back_populates="identities")


class Session(Base):
    """A logged-in browser. Only the sha256 of the cookie token is stored."""

    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    user_agent = Column(String, nullable=True)

    account = relationship("Account", back_populates="sessions")


class PrivacyConsent(Base):
    """One acceptance of the DPDP privacy notice, append-only. The newest row is the
    account's current consent; changing a toggle (or withdrawing) writes a new row, so
    the history of what was agreed, to which notice text, is kept until erasure."""

    __tablename__ = "privacy_consents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    notice_version = Column(String(32), nullable=False)
    # sha256 (hex) of the exact notice text the user was shown.
    notice_hash = Column(String(64), nullable=False)
    # {"github": bool, "resume": bool, "email": bool}
    purposes = Column(JSON, nullable=False)
    accepted_at = Column(DateTime, nullable=False, default=utcnow)
    user_agent = Column(String, nullable=True)

    account = relationship("Account", back_populates="consents")


class OtpCode(Base):
    """An emailed one-time login code. Only its hash is stored."""

    __tablename__ = "otp_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, nullable=False, index=True)
    code_hash = Column(String(64), nullable=False)
    ip = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=utcnow, index=True)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    consumed_at = Column(DateTime, nullable=True)
