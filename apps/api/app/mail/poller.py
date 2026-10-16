"""The background mailbox poller.

Started with the app when ``IMAP_ENABLED`` is set. It sleeps between rounds and
does its blocking IMAP work in a worker thread so the event loop stays free; each
round opens and closes its own database session.
"""

import asyncio
import logging
from typing import Any, Optional

from ..config import settings
from ..db import SessionLocal
from .imap_client import ImapNotConfigured, fetch_recruiter_messages
from .sync import sync_messages

logger = logging.getLogger("hire.mail.poller")


def run_sync_round(limit: Optional[int] = None) -> dict[str, Any]:
    """One fetch-and-apply round. Blocking; safe to call from a worker thread."""
    messages = fetch_recruiter_messages(limit=limit or settings.imap_fetch_limit)
    db = SessionLocal()
    try:
        return sync_messages(db, messages)
    finally:
        db.close()


async def poll_forever(stop_event: asyncio.Event) -> None:
    """Poll the recruiter mailbox until the application shuts down."""
    interval = max(30, settings.imap_poll_seconds)
    logger.info("Recruiter mailbox poller started (every %ss).", interval)

    while not stop_event.is_set():
        try:
            stats = await asyncio.to_thread(run_sync_round)
            if stats["moved"]:
                logger.info("Mail sync moved %s card(s) on the board.", stats["moved"])
        except ImapNotConfigured as exc:
            logger.warning("Recruiter mailbox poller stopping: %s", exc)
            return
        except Exception:  # a flaky mailbox must never take the API down
            logger.exception("Recruiter mailbox poll failed; retrying next round.")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue
