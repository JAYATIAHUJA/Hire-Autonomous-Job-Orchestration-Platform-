"""Background worker: runs job discovery on a fixed interval and executes queued
Proof-of-Work GitHub analyses.

Phase 0 keeps the worker in the API package so both share models and settings.
It moves to ``apps/worker`` when the domain code is split into ``packages/``
(Phase 1). The Postgres SKIP LOCKED job queue and the Run engine arrive in Phase 4;
PoW runs already poll ``pow_runs`` that way (see ``services/pow_service``).

Run with ``python -m app.worker``.
"""

import asyncio
import logging
import signal
from typing import Optional

from .auth.tokens import register_github_providers
from .config import settings
from .db import SessionLocal
from .jobs.pipeline import run_discovery_cycle
from .services import pow_service

logger = logging.getLogger("hire.worker")


async def discovery_round() -> dict[str, int]:
    db = SessionLocal()
    try:
        return await run_discovery_cycle(db, limit=settings.discovery_batch_size)
    finally:
        db.close()


async def pow_round() -> Optional[int]:
    """Execute one queued PoW run; None when the queue is empty."""
    return await pow_service.process_next(SessionLocal)


async def _sleep_or_stop(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


async def discovery_loop(stop: asyncio.Event) -> None:
    logger.info("discovery every %ss", settings.discovery_interval_seconds)
    while not stop.is_set():
        try:
            stats = await discovery_round()
            logger.info("discovery round: %s", stats)
        except Exception:  # noqa: BLE001 - one bad round must not kill the worker
            logger.exception("discovery round failed")
        await _sleep_or_stop(stop, settings.discovery_interval_seconds)


async def pow_loop(stop: asyncio.Event) -> None:
    logger.info("polling PoW runs every %ss", settings.pow_poll_seconds)
    while not stop.is_set():
        try:
            run_id = await pow_round()
            if run_id is not None:
                logger.info("pow run %s finished", run_id)
                continue  # drain the queue before sleeping
        except Exception:  # noqa: BLE001 - one bad run must not kill the worker
            logger.exception("pow round failed")
        await _sleep_or_stop(stop, settings.pow_poll_seconds)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows event loops don't support signal handlers
            pass

    register_github_providers()  # PoW runs use the account's own GitHub token when linked
    logger.info("worker started")
    await asyncio.gather(discovery_loop(stop), pow_loop(stop))
    logger.info("worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
