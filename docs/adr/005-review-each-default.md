# ADR-005: "Review each" is the default; Autopilot is earned

- Status: Accepted (2026-10-15). Confirms decision 1 in PLAN.md §19.
- Plan: PLAN.md §3.2

## Context
A wrong answer sent to an employer can't be taken back. Trust has to be built before Hire submits
without the user looking.

## Decision
- **Review mode** applies to each user's first 10 applications, and always to Tier B and C. The agent fills the form, stops before Submit, and the user taps Submit on the review screen (R2).
- After 10, Hire *offers* **Autopilot**, opt-in per rule. Autopilot submits only when *all* of these hold: the ATS is Tier A; every required field comes from confirmed facts or the answer bank (no LLM drafts in knockout fields); fit ≥ the user's floor (default 70); no ghost or eligibility flags; the per-company cap is not hit.
- Any deviation during a run drops it back to Review mode.

## Consequences
- Slower time-to-value for the first week. The question sheet and pre-flight (ADR-002) keep each review short.
- The "0 wrong-answer incidents" gate for M2 is measured in Review mode before Autopilot is offered to anyone.
