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
from .jobs import discovery
from .jobs.pipeline import run_discovery_cycle
from .services import pow_service
from .apply import runner as apply_runner
from .facts.storage import get_object_store

logger = logging.getLogger("hire.worker")


async def discovery_round() -> Optional[dict[str, int]]:
    """Run discovery if one was requested or one is due; None when there is nothing to do."""
    db = SessionLocal()
    try:
        run = discovery.claim_run(db)
        if run is None:
            return None
        try:
            stats = await run_discovery_cycle(db, limit=settings.discovery_batch_size, run=run)
        except Exception as exc:  # noqa: BLE001 - recorded on the run, then re-raised for the log
            db.rollback()
            discovery.finish_run(db, run, error=f"{type(exc).__name__}: {exc}"[:500])
            raise
        discovery.finish_run(db, run, stats)
        return stats
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
    logger.info("discovery every %ss, or on request", settings.discovery_interval_seconds)
    while not stop.is_set():
        try:
            stats = await discovery_round()
            if stats is not None:
                logger.info("discovery round: %s", stats)
        except Exception:  # noqa: BLE001 - one bad round must not kill the worker
            logger.exception("discovery round failed")
        await _sleep_or_stop(stop, settings.discovery_poll_seconds)


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


async def apply_loop(stop: asyncio.Event) -> None:
    """Fill (and, once confirmed, submit) application forms, one at a time."""
    logger.info("apply runs: polling every 3s")
    store = get_object_store()
    while not stop.is_set():
        try:
            run_id = await asyncio.to_thread(apply_runner.process_next, SessionLocal, store)
            if run_id is not None:
                logger.info("apply run %s advanced", run_id)
                continue
        except Exception:  # noqa: BLE001 - one bad run must not kill the worker
            logger.exception("apply round failed")
        await _sleep_or_stop(stop, 3.0)


async def _sleep_or_stop(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


def run_worker_tasks(stop: asyncio.Event) -> asyncio.Future:
    """The three loops as one awaitable future. Used by ``main`` and, on hosts that
    only run one process (a free Render web service), by the API's lifespan."""
    return asyncio.gather(discovery_loop(stop), pow_loop(stop), apply_loop(stop))


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
    worker = run_worker_tasks(stop)
    await stop.wait()
    worker.cancel()
    logger.info("worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
