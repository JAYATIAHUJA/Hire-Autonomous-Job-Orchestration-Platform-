"""Thin IMAP reader for the recruiter mailbox.

Uses only the standard library (``imaplib`` + ``email``) so the tracker needs no
extra dependency and no mail-provider API key — any IMAP inbox with an app
password works. Message parsing is split out from the network call so it can be
tested against raw fixtures without a live server.
"""

import email
import imaplib
from dataclasses import dataclass
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parsedate_to_datetime
from typing import Any, Optional

from ..config import settings


class ImapNotConfigured(RuntimeError):
    """Raised when a sync is requested but no mailbox credentials are set."""


@dataclass(frozen=True)
class ImapConfig:
    host: str
    port: int
    username: str
    password: str
    mailbox: str = "INBOX"
    use_ssl: bool = True
    search: str = "UNSEEN"


def config_from_settings() -> ImapConfig:
    """Build a connection config from the environment, or explain what is missing."""
    missing = [
        name
        for name, value in (
            ("IMAP_HOST", settings.imap_host),
            ("IMAP_USER", settings.imap_user),
            ("IMAP_PASSWORD", settings.imap_password),
        )
        if not value
    ]
    if missing:
        raise ImapNotConfigured("Missing mailbox settings: " + ", ".join(missing))

    return ImapConfig(
        host=settings.imap_host,
        port=settings.imap_port,
        username=settings.imap_user,
        password=settings.imap_password,
        mailbox=settings.imap_mailbox,
        use_ssl=settings.imap_use_ssl,
        search=settings.imap_search,
    )


def decode_value(raw: Optional[str]) -> str:
    """Decode an RFC 2047 encoded header into plain text."""
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return str(raw)


def extract_body(msg: Message) -> str:
    """Best-effort plain-text body, preferring text/plain over the HTML alternative."""
    if not msg.is_multipart():
        payload = msg.get_payload(decode=True)
        if payload is None:
            return str(msg.get_payload())
        return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")

    html_fallback = ""
    for part in msg.walk():
        if part.get_content_maintype() == "multipart" or part.get_filename():
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if part.get_content_type() == "text/plain":
            return text
        if part.get_content_type() == "text/html" and not html_fallback:
            html_fallback = text

    return html_fallback


def parse_message(uid: str, raw_bytes: bytes) -> dict[str, Any]:
    """Turn a raw RFC822 message into the dict the sync layer consumes."""
    msg = email.message_from_bytes(raw_bytes)

    received_at = None
    if msg.get("Date"):
        try:
            received_at = parsedate_to_datetime(msg["Date"]).isoformat()
        except (TypeError, ValueError):
            received_at = None

    return {
        "uid": uid,
        "from_address": decode_value(msg.get("From")),
        "subject": decode_value(msg.get("Subject")),
        "body": extract_body(msg),
        "received_at": received_at,
    }


def fetch_recruiter_messages(config: Optional[ImapConfig] = None, limit: int = 25) -> list[dict[str, Any]]:
    """Fetch the most recent matching messages from the configured mailbox.

    Blocking by design; the poller runs it in a worker thread.
    """
    cfg = config or config_from_settings()
    client_cls = imaplib.IMAP4_SSL if cfg.use_ssl else imaplib.IMAP4
    messages: list[dict[str, Any]] = []

    client = client_cls(cfg.host, cfg.port)
    try:
        client.login(cfg.username, cfg.password)
        # Read-only: the tracker must never mark a candidate's mail as seen.
        client.select(cfg.mailbox, readonly=True)

        status, data = client.search(None, cfg.search)
        if status != "OK" or not data or not data[0]:
            return []

        uids = data[0].split()[-limit:]
        for uid in uids:
            status, payload = client.fetch(uid, "(RFC822)")
            if status != "OK" or not payload or not isinstance(payload[0], tuple):
                continue
            messages.append(parse_message(uid.decode(), payload[0][1]))
    finally:
        try:
            client.logout()
        except Exception:
            pass

    return messages
