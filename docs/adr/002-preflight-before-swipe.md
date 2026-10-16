# ADR-002: Pre-flight the application form before the card is shown

- Status: Accepted (2026-10-15)
- Plan: PLAN.md §5.8, §5.9

## Context
A browser agent that stops in the middle of a run to ask "What is your notice period?" is slow,
expensive and annoying. Most ATS forms can be read *before* applying: Greenhouse exposes its
questions through `?questions=true`, and Lever and Ashby forms can be scanned once with a headless DOM pass.

## Decision
- Before a job reaches the deck, fetch its form schema (cached per `(ats, requisition)` and shared across users).
- Classify every field: identity, canonical question (answer bank), EEO, free text, or knockout/eligibility.
- Resolve answers from the user's confirmed fact vault and answer bank. Anything unresolved becomes `required_unknowns[]`. That drives a card badge and a small question sheet shown right after the swipe.
- Knockout fields accept only confirmed answers, never an LLM draft. If a mandatory answer is impossible (for example, it requires a citizenship the user doesn't have), the job is gated out of the deck.

## Consequences
- Runs rarely need a human mid-way; Tier A runs can be fully deterministic.
- Schema fetching becomes part of ingestion cost and of adapter health monitoring.
- Workday and unknown sites need a dry-run scan in an Apply Computer, which costs more, so it is done lazily and only for top cards.
