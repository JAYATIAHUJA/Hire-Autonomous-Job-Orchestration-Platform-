"""Encryption at rest for OAuth tokens (Fernet: AES-128-CBC + HMAC-SHA256)."""

from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from ..config import settings


class EncryptionNotConfigured(RuntimeError):
    """TOKEN_ENCRYPTION_KEY is missing or not a valid Fernet key."""


def _fernet() -> Fernet:
    key = (settings.token_encryption_key or "").strip()
    if not key:
        raise EncryptionNotConfigured(
            "TOKEN_ENCRYPTION_KEY is not set. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise EncryptionNotConfigured("TOKEN_ENCRYPTION_KEY is not a valid Fernet key.") from exc


def ensure_encryption_key() -> None:
    _fernet()


def encrypt_token(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_token(ciphertext: Optional[str]) -> Optional[str]:
    """The plaintext token, or None if absent or unreadable (e.g. after a key rotation)."""
    if not ciphertext:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, EncryptionNotConfigured):
        return None
