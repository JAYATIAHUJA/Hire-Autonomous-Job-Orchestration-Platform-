"""Background worker: runs job discovery on a fixed interval.

Phase 0 keeps the worker in the API package so both share models and settings.
It moves to ``apps/worker`` when the domain code is split into ``packages/``
(Phase 1). The Postgres SKIP LOCKED job queue and the Run engine arrive in Phase 4.

Run with ``python -m app.worker``.
"""

import asyncio
import logging
import signal

from .config import settings
from .db import SessionLocal
from .jobs.pipeline import run_discovery_cycle

logger = logging.getLogger("hire.worker")


async def discovery_round() -> dict[str, int]:
    db = SessionLocal()
    try:
        return await run_discovery_cycle(db, limit=settings.discovery_batch_size)
    finally:
        db.close()


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows event loops don't support signal handlers
            pass

    logger.info("worker started; discovery every %ss", settings.discovery_interval_seconds)
    while not stop.is_set():
        try:
            stats = await discovery_round()
            logger.info("discovery round: %s", stats)
        except Exception:  # noqa: BLE001 - one bad round must not kill the worker
            logger.exception("discovery round failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.discovery_interval_seconds)
        except asyncio.TimeoutError:
            pass
    logger.info("worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
