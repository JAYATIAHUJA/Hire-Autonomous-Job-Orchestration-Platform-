# ADR-007: One durable Run engine; never auto-replay a crashed run

- Status: Accepted (2026-10-15)
- Plan: PLAN.md §5.11. Design from open-dots, **clean-room re-implementation** (open-dots has no licence).

## Context
Apply runs, chat turns and schedules all need the same things: durable progress, an event stream
that survives disconnects, human requests (approve, answer, take over, type a secret, OTP) and
crash recovery. An apply run is special: replaying one after a crash can **submit twice**.

## Decision
- One engine with four tables: `runs`, `attempts` (a partial unique index allows one running attempt per run; lease via `owner_token` and `heartbeat_at`), `run_events` (gap-free `seq` per run), and `human_requests`.
- Events are **stored before they are broadcast**. SSE at `GET /runs/{id}/events/stream` resumes from `Last-Event-ID`. Redis pub/sub only wakes subscribers; Postgres is the source of truth.
- A lost lease means the attempt writes nothing more and stops its computer actions.
- `sweep_stale` marks dead attempts `interrupted` and **never replays them automatically**. A retry is a new attempt that first checks "was this already submitted?" (confirmation email, ATS status page).
- The run deadline pauses while a human request is pending.
- Queue: Postgres `FOR UPDATE SKIP LOCKED`, with enqueue in the same transaction as the swipe. Temporal only if workflows outgrow this.

## Consequences
- Some crashed runs need a human decision to retry. That's the price of never double-submitting.
- No code may be copied from open-dots until its author adds a licence (outreach draft in `docs/outreach/`).
