import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import init_db
from .mail.poller import poll_forever
from .routers import applications, jobs, profile

logger = logging.getLogger("hire")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()

    # Objective 3: the recruiter mailbox reader runs alongside the API, moving
    # cards on the board as replies land. Opt in with IMAP_ENABLED.
    stop_event = asyncio.Event()
    poller: asyncio.Task | None = None
    if settings.imap_enabled:
        poller = asyncio.create_task(poll_forever(stop_event))
    else:
        logger.info("IMAP_ENABLED is off - recruiter replies only sync via POST /api/mail/sync.")

    try:
        yield
    finally:
        stop_event.set()
        if poller:
            poller.cancel()
            try:
                await poller
            except asyncio.CancelledError:
                pass


app = FastAPI(title="Hire-Unplug — Autonomous Job Orchestration Platform", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profile.router)
app.include_router(jobs.router)
app.include_router(jobs.router, prefix="/api")
app.include_router(applications.router)


@app.get("/health")
def health():
    return {"status": "ok"}
