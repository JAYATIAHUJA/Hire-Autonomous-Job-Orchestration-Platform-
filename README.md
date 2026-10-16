# Hire

*Swipe right. Hire applies. You stay in control.*

Hire is a mobile-first job app (PWA) for software engineers and students, India-first.
It builds a verified profile from your real GitHub work, deals a daily deck of real, non-ghost
jobs, and on a right swipe prepares a grounded application. You sign a consent receipt, and a
cloud browser agent then fills the employer's own ATS form. You can watch it live or take over.

The full plan lives outside this repo, in `../PLAN.md`. Decisions are recorded as ADRs in `docs/adr/`.

## Status: Phase 0 (foundation)

| Area | State |
|---|---|
| `apps/api` | The original Hire FastAPI backend (PoW engine, jobs, ghost filter, swipe/consent, Kanban, IMAP). Bugs B1–B4, B6, B8 and B10 are fixed and have regression tests. Postgres via Alembic. |
| `apps/web` | The original Hire React PWA (profile, jobs, swipe deck, pipeline). |
| `apps/api/app/worker.py` | Background worker: periodic job discovery. The job queue and the Run engine arrive in Phase 4. |
| `apps/supervisor`, `apps/computer` | Built from CopilotKit/OpenBot at a pinned revision (MIT). They become real forks in Phase 4. |
| `lab/mock-ats` | A Greenhouse-shaped mock employer board, for testing the apply engine without real employers. |
| `packages/*` | Not created yet. Domain code is split out of `apps/api` in Phase 1. |

## Run it

Requires Docker and Python 3.12.

```sh
python scripts/dev.py            # first run writes .env with random secrets, then starts the stack
python scripts/dev.py --computers   # also the OpenBot supervisor + computer image (slow first build)
python scripts/dev.py --down
```

| Service | URL |
|---|---|
| Web (Vite dev server) | http://localhost:5173 |
| API | http://localhost:8100 (docs at `/docs`) |
| Mock ATS | http://localhost:8180/boards/acme/jobs/4001 |
| Postgres | `localhost:54329` (user/password/db: `hire`) |
| Redis | `localhost:63790` |
| S3 (SeaweedFS) | http://localhost:58333 (bucket `hire-dev`) |

## Develop without Docker

```sh
python -m venv .venv && .venv/Scripts/pip install -r apps/api/requirements.txt   # Windows path; use .venv/bin on macOS/Linux
cd apps/api && ../../.venv/Scripts/python -m pytest -q        # hermetic: no network
cd apps/web && npm ci && npm run dev                          # proxies /api to VITE_API_PROXY (default :8000)
```

Running the API by hand needs `CONSENT_SIGNING_SECRET` (32+ characters). It refuses to start without one.

## Repository layout (target, PLAN.md §13.1)

```
apps/api        FastAPI (routers, auth, SSE, WS proxy)
apps/worker     ingest, ghost, match, pow, tailor, preflight, apply, mail, agent   (Phase 1+)
apps/web        React PWA
apps/computer   fork of OpenBot agent-computer                                     (Phase 4)
apps/supervisor fork of OpenBot supervisor                                         (Phase 4)
packages/       core, pow, sources, adapters, prompts, schemas                     (Phase 1+)
lab/mock-ats    ATS clones + chaos scenarios
evals/          datasets + graders                                                 (Phase 3+)
infra/          terraform, gVisor, dashboards                                      (Phase 6)
docs/           ADRs, threat model, DPDP notice, runbooks
```

## Licence

Proprietary. All rights reserved. See `LICENSE`. Third-party components and their licences are listed in `NOTICE`.
