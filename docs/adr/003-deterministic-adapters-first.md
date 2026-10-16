# ADR-003: Deterministic adapters first, LLM browser agent as fallback

- Status: Accepted (2026-10-15)
- Plan: PLAN.md §5.13, §8.1, §8.2, §11.1

## Context
Greenhouse, Lever, Ashby and SmartRecruiters forms are structured and predictable. Filling them
with an LLM agent step by step costs about $0.60 per run and is less reliable than code. Workday,
iCIMS and custom career sites vary too much for hand-written code alone.

## Decision
- **Tier A (deterministic adapter):** navigate to the apply URL, fill from the schema-mapped packet (by label or name), upload, read every value back from the DOM, screenshot each page, pass the Submit gate (ADR-004), then detect confirmation. At most one LLM call for field mapping.
- **Tier B (LLM browser agent):** Claude (`claude-opus-5-5`) with computer tools over the OpenBot snapshot/ref API, plus vendor playbooks (Workday account creation, OTP, multi-step wizard).
- Adapters are versioned and tested nightly against the Mock ATS Lab, and by dry runs on real live forms (fill everything, never submit). If an adapter's success rate drops below 90%, that vendor is auto-demoted to Tier B and on-call is alerted.

## Consequences
- This is the biggest cost lever: about $0.03 per Tier A fill against about $0.60 per Tier B run.
- Adapters need maintenance whenever an ATS changes its markup. The Mock ATS Lab and canaries are mandatory, not optional.
- Every adapter has to emit the same run events as the agent, so the review screen and live view work for both.
